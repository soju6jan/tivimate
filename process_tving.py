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
from tool_base import d

# 패키지
from .plugin import P
from .process_base import ProcessBase
logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting
#########################################################

from support.site.tving import SupportTving

@P.blueprint.route('/tving_live.m3u8', methods=['GET'])
def tving_live():
    quality = SupportTving.ins.get_quality_to_tving(ModelSetting.get('tving_quality'))
    c_id = request.args.get('channelid')
    data = SupportTving.ins.get_info(c_id, quality)
    url = data['url']
    if data['drm'] == False:
        data = requests.get(url).text
        temp = url.split('playlist.m3u8')
        rate = ['chunklist_b5128000.m3u8', 'chunklist_b1628000.m3u8', 'chunklist_b1228000.m3u8', 'chunklist_b1128000.m3u8', 'chunklist_b628000.m3u8', 'chunklist_b378000.m3u8', 'chunklist_b7692000.m3u8', 'chunklist_b3192000.m3u8', 'chunklist_b2442000.m3u8', 'chunklist_b1692000.m3u8', 'chunklist_b942000.m3u8', 'chunklist_b567000.m3u8', 'chunklist_b379500.m3u8']
        for r in rate:
            if data.find(r) != -1:
                url1 = '%s%s%s' % (temp[0], r, temp[1])
                data1 = requests.get(url1).text
                data1 = data1.replace('media', '%smedia' % temp[0]).replace('.ts', '.ts%s' % temp[1])
                return data1
        return url


class ProcessTving(ProcessBase):
    unique = '2'
    saved = {'live':{}, 'vod':{}, 'series':{}, 'live_channel_list':None}
    @classmethod 
    def scheduler_function(cls, mode='scheduler'):
        try:
            if ModelSetting.get_bool('tving_use') == False:
                return
            #if mode == 'force' or cls.live_list is None:
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
                if cls.is_working_time(item, mode) == False:
                    continue
                else:
                    cls.saved['live'][category_id] = []
                    cls.saved['live_channel_list'] = OrderedDict()
                live_list = SupportTving.ins.get_live_list(list_type=item['category']) #, order='name')
                if live_list is None or len(live_list) == 0:
                    break
                for live in live_list:
                    if ModelSetting.get('drm_include') == False and live['is_drm']:
                        continue
                    xc_id = ModelTvingMap.get_xc_id('live', live['id'], live['is_drm'])
                    name = live['title']
                    if  live['is_drm'] and ModelSetting.get_bool('drm_notify'):
                        name += '(D)'
                    entity = {
                        'name' : name,
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
                    cls.saved['live_channel_list'][live['id']] = {'name':entity['name'], 'icon':entity['stream_icon'], 'list':[]}
                    cls.saved['live'][category_id].append(entity)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
            finally:
                cls.live_list += cls.saved['live'][category_id]
                cls.live_channel_list = cls.saved['live_channel_list']
        logger.debug('Tving live count : %s', len(cls.live_list))
        cls.make_channel_epg_data()


    @classmethod
    def make_vod_data(cls, mode):
        cls.vod_categories = []
        cls.vod_list = []
        
        for item in cls.make_json(ModelSetting.get('tving_vod')):
            if ModelSetting.get_bool('tving_is_adult') == False and 'is_adult' in item and item['is_adult']:
                continue
            try:
                category_id =  str(item['id']) + ProcessTving.unique
                cls.vod_categories.append({'category_id' : category_id, 'category_name':item['title'], 'parent_id':0})
                if cls.is_working_time(item, mode) == False:
                    continue
                else:
                    cls.saved['vod'][category_id] = []
                page = 1
                category_count = 0
                while True:
                    vod_list = SupportTving.ins.get_movie_list(page=page, category=item['category'])
                    if vod_list is None or len(vod_list['result']) == 0:
                        break
                    id_type = 'vod_' + item['category']
                    for vod in vod_list['result']:
                        if ModelSetting.get('drm_include') == False and vod['movie']['drm_yn'] == 'Y':
                            continue
                        xc_id = ModelTvingMap.get_xc_id('vod', vod['movie']['code'], is_drm=(vod['movie']['drm_yn'] == 'Y'))
                        name = vod['vod_name']['ko']
                        if vod['movie']['drm_yn'] == 'Y' and ModelSetting.get_bool('drm_notify'):
                            name += '(D)'
                        #logger.warning(d(vod['movie']))
                        #backdrop = ''
                        #for img in vod['movie']['image']:
                        #    if img['code'] in ['CAIM0400', 'CAIM0700']:
                        #        backdrop = 'https://image.tving.com' + img['url']

                        entity = {
                            'name' : name,
                            "stream_type":"movie",
                            'stream_id' : xc_id,
                            'stream_icon' : 'https://image.tving.com' + vod['movie']['image'][-1]['url'],
                            'category_id' : category_id,
                            'is_adult' : '0',
                        }
                        #CAIM0400 CAIM0700
                        cls.saved['vod'][category_id].append(entity)
                        category_count += 1

                    page += 1
                    if category_count >= item['max_count']:
                        break
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
            finally:
                logger.debug('title : %s , append : %s', item['title'], len(cls.saved['vod'][category_id]))
                cls.vod_list += cls.saved['vod'][category_id]
        logger.debug('TVING vod count : %s', len(cls.vod_list))

    @classmethod
    def make_series_data(cls, mode):
        cls.series_categories = []
        cls.series_list = []
        timestamp = int(time.time())
        count = 0
        for item in cls.make_json(ModelSetting.get('tving_series')):
            if ModelSetting.get_bool('tving_is_adult') == False and 'is_adult' in item and item['is_adult']:
                continue
            category_id =  str(item['id']) + ProcessTving.unique
            cls.series_categories.append({'category_id' : category_id, 'category_name':item['title'], 'parent_id':0})
            try:
                if cls.is_working_time(item, mode) == False:
                    continue
                else:
                    cls.saved['series'][category_id] = []
                page = 1
                category_count = 0
                while True:   
                    #logger.error(item['category'])
                    #logger.error(page)
                    episode_list = SupportTving.ins.get_vod_list_genre(genre=item['category'], page=page)
                    if episode_list is None or len(episode_list['result']) == 0:
                        break                  
                    for idx, episode in enumerate(episode_list['result']):
                        id_type = 'series_%s' % item['category']
                        xc_id = ModelTvingMap.get_xc_id(id_type, episode['program']['code'], is_drm=('drm_yn' in episode['episode'] and episode['episode']['drm_yn'] == 'Y'))
                        if ModelSetting.get('drm_include') == False and episode['episode']['drm_yn'] == 'Y':
                            continue
                        if ModelSetting.get_bool('tving_is_adult') == False and episode['program']['adult_yn'] == 'Y':
                            continue
                        image_url = None
                        for tmp in episode['program']['image']:
                            if tmp['code']  == 'CAIP0900':
                                image_url = 'https://image.tving.com' + tmp['url']
                                break
                        name = episode['program']['name']['ko']
                        if 'drm_yn' in episode['episode'] and episode['episode']['drm_yn'] == 'Y' and ModelSetting.get_bool('drm_notify'):
                            name += '(D)'
                        entity = {
                            'name' : name,
                            'series_id' : xc_id, 
                            'cover' : image_url,
                            'category_id' : category_id,
                            'last_modified' : timestamp - count
                        }
                        #logger.warning(entity['name'])
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
            backdrop = ''
            for img in program_data['content']['info']['movie']['image']:
                if img['code'] in ['CAIM0400', 'CAIM0700']:
                    backdrop = 'https://image.tving.com' + img['url']
                    break
            ret = {
                'info' : {
                    'plot' : program_data['content']['info']['movie']['story']['ko'], 
                    'cast' : ', '.join(program_data['content']['info']['movie']['actor']),
                    'director' : ', '.join(program_data['content']['info']['movie']['director']),
                    'duration_secs' : program_data['content']['info']['movie']['duration'],
                    'backdrop_path' : backdrop,
                },
                'movie_data' : {
                    'name' : program_data['content']['info']['movie']['name']['ko'],
                    "stream_type":"movie",
                    'stream_id' : vod_id,
                    'container_extension': 'mpd' if db_item.is_drm else 'm3u8', # 이거 필수
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
            #logger.warning(d(program_data))
            backdrop = ''
            for img in program_data['image']:
                if img['code'] in ['CAIP0400', 'CAIP0700']:
                    backdrop = 'https://image.tving.com' + img['url']
                    break
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
                    'plot' : program_data['synopsis']['ko'], 
                    'cast' : ', '.join(program_data['actor']),
                    'director' : ', '.join(program_data['director']),
                    'genre' : program_data['category1_name']['ko'] + ', ' + program_data['category2_name']['ko'],
                    'releasedate' : program_data['broad_dt'] ,
                    'backdrop_path' : backdrop,
                },
                'episodes': {'1' : []},
            }
            page = 1
            index = 1
            episode_data = SupportTving.ins.get_frequency_programid(content_id, page=page)

            ret['info']['genre'] += '   ' + episode_data['result'][0]['channel']['name']['ko']
            for episode in list(reversed(episode_data['result'])):
                item = {
                    "id" : ModelTvingMap.get_xc_id('episode', episode['episode']['code']),
                    "episode_num": episode['episode']['frequency'],
                    "title" : u'%s회 (%s)' % (episode['episode']['frequency'], cls.date_change(episode['episode']['broadcast_date'])),
                    "container_extension": 'mpd' if db_item.is_drm else 'm3u8',
                    "info": {
                        "movie_image" : 'https://image.tving.com' + episode['episode']['image'][0]['url'] if len(episode['episode']['image']) > 0 else '',
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
    def get_streaming_url(cls, xc_id, content_type, extension="m3u8"):
        db_item = ModelTvingMap.get_by_xc_id(xc_id)
        content_id = db_item.tving_id
        data = SupportTving.ins.get_info(content_id, SupportTving.ins.get_quality_to_tving(ModelSetting.get('tving_quality')))
        if content_type == 'live':
            if db_item.is_drm:
                return data['play_info']
            else:
                ret = f"{SystemModelSetting.get('ddns')}/tivimate/tving_live.m3u8?channelid={content_id}"
            return ret
        elif content_type == 'vod':
            if extension == "mpd":
                return data['play_info']
            else:
                return data['url']
        else:
            if extension == "mpd":
                return data['play_info']
            else:
                return data['url']


    @classmethod
    def make_channel_epg_data(cls):
        try:
            current_dt = datetime.now()
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
                        data = SupportTving.ins.get_schedules(ch, date_param, start_time, end_time)
                        for ch in data['result']:
                            if ch['schedules'] is not None:
                                for schedule in ch['schedules']:
                                    try:
                                        entity = {}
                                        entity['start_time'] = datetime.strptime(str(schedule['broadcast_start_time']), '%Y%m%d%H%M%S')
                                        entity['end_time'] = datetime.strptime(str(schedule['broadcast_end_time']), '%Y%m%d%H%M%S')
                                        entity['title'] = schedule['program']['name']['ko']
                                        if ch['channel_code'] in cls.live_channel_list:
                                            cls.live_channel_list[ch['channel_code']]['list'].append(entity)
                                    except Exception as e: 
                                        logger.error('Exception:%s', e)
                                        logger.error(traceback.format_exc())
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
        else:
            if item.is_drm != is_drm:
                item.is_drm = is_drm
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
            ret.program_data = SupportTving.ins.get_info(ret.tving_id, SupportTving.ins.get_quality_to_tving(ModelSetting.get('tving_quality')))
            db.session.add(ret)
            db.session.commit()
        if ret.id_type.startswith('series') and ret.program_data is None:
            ret.program_data = SupportTving.ins.get_program_programid(ret.tving_id)
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
