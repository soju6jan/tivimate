# -*- coding: utf-8 -*-
#########################################################
# python
import os, sys, traceback, re, json, threading, time, shutil
from datetime import datetime, timedelta
from collections import OrderedDict

# third-party
from flask import request, render_template, jsonify, redirect, Response
from sqlalchemy import or_, and_, func, not_, desc
from lxml import etree as ET
import requests

# sjva 공용
from framework import db, scheduler, path_data, socketio, SystemModelSetting, app
from framework.util import Util

# 패키지
from .plugin import P
from .process_base import ProcessBase
logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting
#########################################################

import framework.tving.api as Tving

@P.blueprint.route('/tving_live.m3u8', methods=['GET'])
def tving_live():
    quality = Tving.get_quality_to_tving(ModelSetting.get('tving_quality'))
    c_id = request.args.get('channelid')
    proxy = ModelSetting.get('tving_proxy_url') if ModelSetting.get_bool('tving_use_proxy') else None
    data, url = Tving.get_episode_json(c_id, quality, ModelSetting.get('tving_login_data'), proxy=proxy, is_live=True)
    if data['body']['stream']['drm_yn'] == 'N':
        data = requests.get(url).text
        temp = url.split('playlist.m3u8')
        rate = ['chunklist_b5128000.m3u8', 'chunklist_b1628000.m3u8', 'chunklist_b1228000.m3u8', 'chunklist_b1128000.m3u8', 'chunklist_b628000.m3u8', 'chunklist_b378000.m3u8']
        for r in rate:
            if data.find(r) != -1:
                url1 = '%s%s%s' % (temp[0], r, temp[1])
                data1 = requests.get(url1).text
                data1 = data1.replace('media', '%smedia' % temp[0]).replace('.ts', '.ts%s' % temp[1])
                return data1
        return url
"""
    else:
        #return Response(url, mimetype='application/dash+xml')
        import framework.common.util as CommonUtil
        filename = os.path.join(path_data, 'output', '%s.strm' % c_id)
        CommonUtil.write_file(url, filename) 
        ret = '/file/data/output/%s.strm' % c_id
        if SystemModelSetting.get_bool('auth_use_apikey'):
            ret += '?apikey=%s' % SystemModelSetting.get('auth_apikey')
        return redirect(ret)

@P.blueprint.route('/proxy', methods=['POST'])
def proxy():
    proxy = ModelSetting.get('tving_proxy_url') if ModelSetting.get_bool('tving_use_proxy') else None
    if proxy is not None:
        proxies={"https": proxy, 'http':proxy}
    data = requests.get(request.form['url'], proxies=proxies).json()
    return jsonify(data)
"""



class ProcessTving(ProcessBase):
    unique = '2'
    saved = {'vod':{}, 'series':{}}
    @classmethod 
    def scheduler_function(cls, mode='scheduler'):
        try:
            #db.session.query(ModelTvingMap).delete()
            #db.session.commit()
            if ModelSetting.get_bool('tving_use') == False:
                return
            if mode == 'force' or cls.live_list is None:
                cls.make_live_data(mode)
            cls.make_vod_data(mode)
            cls.make_series_data(mode)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @classmethod
    def make_live_data(cls, mode):
        cls.live_categories = []
        cls.live_list = []
        cls.live_channel_list = OrderedDict()
        
        for item in cls.make_json(ModelSetting.get('tving_live')):
            try:
                category_id =  str(item['id']) + ProcessTving.unique
                cls.live_categories.append({'category_id' : category_id, 'category_name':item['title'], 'parent_id':0})
                live_list = Tving.get_live_list(list_type=item['category'], order='name')
                #live_list = Tving.get_live_list(list_type=item['category'], except_drm=False)
                if live_list is None or len(live_list) == 0:
                    break
                for live in live_list:
                    xc_id = ModelTvingMap.get_xc_id('live', live['id'], live['is_drm'])
                    entity = {
                        'name' : '%s%s' % (live['title'], "(D)" if live['is_drm'] else ''),
                        "stream_type":"live",
                        "stream_id":"live",
                        'stream_id' : xc_id,
                        'stream_icon' : live['img'],
                        "epg_channel_id" : live['id'],
                        "added":"1492282762",
                        "is_adult":"0",
                        "category_id":category_id,
                        "custom_sid":"",
                        "tv_archive":0,
                        "direct_source":"",
                        "tv_archive_duration":0
                    }
                    cls.live_channel_list[live['id']] = {'name':entity['name'], 'icon':entity['stream_icon'], 'list':[]}
                    cls.live_list.append(entity)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        logger.debug('Tving live count : %s', len(cls.live_list))
        cls.make_channel_epg_data()



    @classmethod
    def make_vod_data(cls, mode):
        cls.vod_categories = []
        cls.vod_list = []
        
        for item in cls.make_json(ModelSetting.get('tving_vod')):
            logger.debug('TVING vod %s', item['title'])
            if ModelSetting.get_bool('tving_is_adult') == False and 'is_adult' in item and item['is_adult']:
                continue
            try:
                category_id =  str(item['id']) + ProcessTving.unique
                cls.vod_categories.append({'category_id' : category_id, 'category_name':item['title'], 'parent_id':0})
                if cls.is_working_time(item, mode) == False:
                    logger.debug('work no')
                    continue
                else:
                    cls.saved['vod'][category_id] = []
                page = 1
                category_count = 0
                while True:
                    vod_list = Tving.get_movies(page=page, category=item['category'])['body']
                    if vod_list is None or len(vod_list['result']) == 0:
                        break
                    id_type = 'vod_' + item['category']
                    for vod in vod_list['result']:
                        #if vod['movie']['drm_yn'] == 'Y':
                        #    continue
                        xc_id = ModelTvingMap.get_xc_id('vod', vod['movie']['code'], is_drm=(vod['movie']['drm_yn'] == 'Y'))
                        #db_item = ModelTvingMap.get_by_xc_id(xc_id)
                        entity = {
                            'name' : vod['vod_name']['ko'] + ("(D)" if vod['movie']['drm_yn'] == 'Y' else ""),
                            "stream_type":"movie",
                            'stream_id' : xc_id,
                            'stream_icon' : 'https://image.tving.com' + vod['movie']['image'][-1]['url'],
                            #'rating' : vod['rating'],
                            'category_id' : category_id,
                            'is_adult' : '0',
                        }
                        cls.saved['vod'][category_id].append(entity)
                        category_count += 1

                    page += 1
                    if category_count >= item['max_count']:
                        break
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
            finally:
                logger.debug('append : %s', len(cls.saved['vod'][category_id]))
                cls.vod_list += cls.saved['vod'][category_id]
        logger.debug('TVING vod count : %s', len(cls.vod_list))

    @classmethod
    def make_series_data(cls, mode):
        cls.series_categories = []
        cls.series_list = []
        timestamp = int(time.time())
        count = 0
        for item in cls.make_json(ModelSetting.get('tving_series')):
            logger.debug('TVING series %s', item['title'])
            if ModelSetting.get_bool('tving_is_adult') == False and 'is_adult' in item and item['is_adult']:
                continue
            category_id =  str(item['id']) + ProcessTving.unique
            cls.series_categories.append({'category_id' : category_id, 'category_name':item['title'], 'parent_id':0})
            try:
                if cls.is_working_time(item, mode) == False:
                    logger.debug('work no')
                    continue
                else:
                    cls.saved['series'][category_id] = []
                page = 1
                category_count = 0
                while True:   
                    episode_list = Tving.get_vod_list2(page=page, genre=item['category'])
                    if episode_list is None or len(episode_list['body']['result']) == 0:
                        break                  
                    for idx, episode in enumerate(episode_list['body']['result']):
                        id_type = 'series_%s' % item['category']
                        xc_id = ModelTvingMap.get_xc_id(id_type, episode['program']['code'])
                        #db = ModelTvingMap.get_by_xc_id(xc_id)
                        if episode['episode']['drm_yn'] == 'Y':
                            continue
                        if ModelSetting.get_bool('tving_is_adult') == False and episode['program']['adult_yn'] == 'Y':
                            continue
                        image_url = None
                        for tmp in episode['program']['image']:
                            if tmp['code']  == 'CAIP0900':
                                image_url = 'https://image.tving.com' + tmp['url']
                                break
                        entity = {
                            'name' : episode['program']['name']['ko'],
                            'series_id' : xc_id, 
                            'cover' : image_url,
                            'category_id' : category_id,
                            'last_modified' : timestamp - count
                        }
                        cls.saved['series'][category_id].append(entity)
                        count += 1
                        category_count += 1
                    page += 1
                    if category_count >= item['max_count']:
                        break 
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
            finally:
                logger.debug('append : %s', len(cls.saved['series'][category_id]))
                cls.series_list += cls.saved['series'][category_id]
        logger.debug('TVING series count : %s', len(cls.series_list))

    @classmethod 
    def get_vod_info(cls, vod_id):
        try:
            db_item = ModelTvingMap.get_by_xc_id(vod_id)
            content_id = db_item.tving_id
            program_data = db_item.program_data
            ret = {
                'info' : {
                    'plot' : program_data['content']['info']['movie']['story']['ko'], 
                    'cast' : ', '.join(program_data['content']['info']['movie']['actor']),
                    'director' : ', '.join(program_data['content']['info']['movie']['director']),
                    #'genre' : ', '.join([x['text'] for x in program_data['genre']['list']]),
                    #'releasedate' : program_data['releasedate'],
                    'duration_secs' : program_data['content']['info']['movie']['duration'],
                },
                'movie_data' : {
                    'name' : program_data['content']['info']['movie']['name']['ko'],
                    "stream_type":"movie",
                    'stream_id' : vod_id,
                    #'container_extension': 'strm' if db_item.is_drm else 'm3u8', # 이거 필수
                    'container_extension': 'm3u',#' if db_item.is_drm else 'm3u8', # 이거 필수
                }
            }
            return ret
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @classmethod
    def date_change(cls, value):
        value = str(value)
        return '%s-%s-%s' % (value[0:4], value[4:6], value[6:8])

    @classmethod 
    def get_series_info(cls, series_id):
        try:
            db_item = ModelTvingMap.get_by_xc_id(series_id)
            content_id = db_item.tving_id
            program_data = db_item.program_data
            ret = {
                'seasons':[
                    {
                        'air-date' : '',
                        'name' : u'시즌 1',
                        'season_number' : 1,
                    }
                ],
                'info' : {
                    "name" : program_data['name']['ko'], 
                    #"cover" : 'https://' + program_data['posterimage'],
                    'plot' : program_data['synopsis']['ko'], 
                    'cast' : ', '.join(program_data['actor']),
                    'director' : ', '.join(program_data['director']),
                    'genre' : program_data['category1_name']['ko'] + ', ' + program_data['category2_name']['ko'],
                    'releasedate' : program_data['broad_dt'] 
                },
                'episodes': {'1' : []},
            }
            page = 1
            index = 1
            #is_first = True
            #while True:
            # 한번에 리턴함
            episode_data = Tving.get_frequency_programid(content_id, page=page)['body']
            ret['info']['genre'] += '   ' + episode_data['result'][0]['channel']['name']['ko']
            for episode in list(reversed(episode_data['result'])):
                item = {
                    "id" : ModelTvingMap.get_xc_id('episode', episode['episode']['code']),
                    "episode_num": episode['episode']['frequency'],
                    "title" : u'%s회 (%s)' % (episode['episode']['frequency'], cls.date_change(episode['episode']['broadcast_date'])),
                    "container_extension": 'mp4',
                    "info": {
                        "movie_image" : 'https://image.tving.com' + episode['episode']['image'][0]['url'] if len(episode['episode']['image']) > 0 else '',
                        #'duration_secs' : episode['playtime'],
                    },
                    "season": 1,
                }
                index += 1
                ret['episodes']['1'].append(item)
            return ret
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @classmethod 
    def get_streaming_url(cls, xc_id, content_type):
        db_item = ModelTvingMap.get_by_xc_id(xc_id)
        content_id = db_item.tving_id
        if content_type == 'live':
            ret = '/tivimate/tving_live.m3u8?channelid=%s' % content_id
            logger.debug(ret)
            return ret
        elif content_type == 'vod':
            data = requests.get('https://sjva.me/sjva/tving.php').json()
            return data['body']['decrypted_url'].replace('<br>', '\n')
        else:
            proxy = ModelSetting.get('tving_proxy_url') if ModelSetting.get_bool('tving_use_proxy') else None
            data, url = Tving.get_episode_json(content_id, Tving.get_quality_to_tving(ModelSetting.get('tving_quality')), ModelSetting.get('tving_login_data'), proxy=proxy)
            return url


    @classmethod
    def make_channel_epg_data(cls):
        try:
            current_dt = datetime.now()
            #nextday = False
            start_dt = datetime(current_dt.year, current_dt.month, current_dt.day, int(current_dt.hour/3)*3, 0, 1)
            for part in range(2):
                for i in range(5):
                    try:
                        tmp = start_dt + timedelta(hours=(i*3))
                        date_param = tmp.strftime('%Y%m%d')
                        start_time = str(tmp.hour).zfill(2) + '0000'
                        end_time = str((tmp + timedelta(hours=3)).hour).zfill(2) + '0000'
                        if app.config['config']['is_py2']:
                            keys = cls.live_channel_list.keys()
                        else:
                            keys = list(cls.live_channel_list.keys())
                        ch = keys[:20] if part == 0 else keys[20:]
                        data = Tving.get_schedules(ch, date_param, start_time, end_time)['body']
                        for ch in data['result']:
                            for schedule in ch['schedules']:
                                entity = {}
                                entity['start_time'] = datetime.strptime(str(schedule['broadcast_start_time']), '%Y%m%d%H%M%S')
                                entity['end_time'] = datetime.strptime(str(schedule['broadcast_end_time']), '%Y%m%d%H%M%S')
                                entity['title'] = schedule['program']['name']['ko']
                                cls.live_channel_list[ch['channel_code']]['list'].append(entity)
                    except Exception as e: 
                        logger.error('Exception:%s', e)
                        logger.error(traceback.format_exc())
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())



class ModelTvingMap(db.Model):
    __tablename__ = '{package_name}_tving_map'.format(package_name=P.package_name)
    __table_args__ = {'mysql_collate': 'utf8_general_ci'}
    __bind_key__ = P.package_name

    xc_id = db.Column(db.Integer, primary_key=True)
    tving_id = db.Column(db.String, nullable=False)
    id_type = db.Column(db.String)
    program_data = db.Column(db.JSON)
    is_drm = db.Column(db.Boolean)
    
    def __init__(self, tving_id, id_type, is_drm):
        self.tving_id = tving_id
        self.id_type = id_type
        self.is_drm = is_drm

    def as_dict(self):
        ret = {x.name: getattr(self, x.name) for x in self.__table__.columns}
        return ret

    @classmethod
    def get_xc_id(cls, id_type, tving_id, is_drm=False):
        item = db.session.query(cls).filter_by(tving_id=tving_id).filter_by(id_type=id_type).first()
        save_flag = False
        if item is None:
            item = ModelTvingMap(tving_id, id_type, is_drm)
            save_flag = True
        if save_flag:
            db.session.add(item)
            db.session.commit()
        return str(item.xc_id) + ProcessTving.unique
    
    @classmethod
    def get_by_xc_id(cls, xc_id):
        xc_id = int(xc_id[:-1])
        ret = db.session.query(cls).filter_by(xc_id=xc_id).first()
        if ret.id_type.startswith('vod') and ret.program_data is None:
            #from sqlalchemy.orm.attributes import flag_modified
            proxy = ModelSetting.get('tving_proxy_url') if ModelSetting.get_bool('tving_use_proxy') else None
            
            ret.program_data = Tving.get_movie_json2(ret.tving_id, '', ModelSetting.get('tving_login_data'), proxy=proxy, quality= Tving.get_quality_to_tving(ModelSetting.get('tving_quality')))['body']

            
            #flag_modified(ret, 'program_data')
            db.session.add(ret)
            db.session.commit()
        if ret.id_type.startswith('series') and ret.program_data is None:
            ret.program_data = Tving.get_program_programid(ret.tving_id)['body']
            db.session.add(ret)
            db.session.commit()
        return ret



tving_default_live = u'''
[티빙]\ncategory = 0
'''

tving_default_vod = u'''
[티빙]\ncategory = live\nmax_count = 100\nfrequency = 72
[티빙]\ncategory = all\nmax_count = 100\nfrequency = 72
'''

tving_default_series = u'''
[티빙]\ncategory = all\nmax_count = 100\nfrequency = 1
[티빙 드라마]\ncategory = PCA\nmax_count = 100\nfrequency = 6
[티빙 예능]\ncategory = PCD\nmax_count = 100\nfrequency = 6
[티빙 해외시리즈]\ncategory = PCPOS\nmax_count = 100\nfrequency = 72
[티빙 디지털오리지널]\ncategory = PCWD\nmax_count = 100\nfrequency = 72
[티빙 교양]\ncategory = PCK\nmax_count = 100\nfrequency = 6
[티빙 키즈/애니]\ncategory = PCC\nmax_count = 100\nfrequency = 6
[티빙 스포츠/취미]\ncategory = PCF\nmax_count = 100\nfrequency = 72
'''