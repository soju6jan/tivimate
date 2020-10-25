# -*- coding: utf-8 -*-
#########################################################
# python
import os, sys, traceback, re, json, threading, time, shutil
from datetime import datetime, timedelta
from collections import OrderedDict

# third-party
from flask import request, render_template, jsonify, redirect
from sqlalchemy import or_, and_, func, not_, desc
from lxml import etree as ET

# sjva 공용
from framework import db, scheduler, path_data, socketio, SystemModelSetting
from framework.util import Util

# 패키지
from .plugin import P
from .process_base import ProcessBase
logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting
#########################################################

import framework.wavve.api as Wavve


class ProcessWavve(ProcessBase):
    unique = '1'
    saved = {'vod':{}, 'series':{}}
    @classmethod 
    def scheduler_function(cls, mode='scheduler'):
        try:
            if ModelSetting.get_bool('wavve_use') == False:
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
        
        for item in cls.make_json(ModelSetting.get('wavve_live')):
            logger.debug('WAVVE live %s', item['title'])
            if ModelSetting.get_bool('wavve_is_adult') == False and 'is_adult' in item and item['is_adult']:
                continue
            try:
                category_id =  str(item['id']) + ProcessWavve.unique
                cls.live_categories.append({'category_id' : category_id, 'category_name':item['title'], 'parent_id':0})
                live_list = Wavve.live_all_channels(genre=item['category'])
                if live_list is None or len(live_list['list']) == 0:
                    break
                id_type = 'live_' + item['category']
                
                for live in live_list['list']:
                    xc_id = ModelWavveMap.get_xc_id(id_type, live['channelid'])
                    entity = {
                        'name' : live['channelname'],
                        "stream_type":"live",
                        "stream_id":"live",
                        'stream_id' : xc_id,
                        'stream_icon' : 'https://' + live['tvimage'],
                        "epg_channel_id" : live['channelid'],
                        "added":"1492282762",
                        "is_adult":"0",
                        "category_id":category_id,
                        "custom_sid":"",
                        "tv_archive":0,
                        "direct_source":"",
                        "tv_archive_duration":0
                    }
                    if live['channelid'] not in cls.live_channel_list:
                        cls.live_channel_list[live['channelid']] = {'name':live['channelname'], 'icon':entity['stream_icon'], 'list':cls.get_channel_epg_data(live['channelid'])}
                        
                    cls.live_list.append(entity)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
            
        logger.debug('WAVVE live count : %s', len(cls.live_list))

    @classmethod
    def make_vod_data(cls, mode):
        cls.vod_categories = []
        cls.vod_list = []
        
        for item in cls.make_json(ModelSetting.get('wavve_vod')):
            logger.debug('WAVVE vod %s', item['title'])
            if ModelSetting.get_bool('wavve_is_adult') == False and 'is_adult' in item and item['is_adult']:
                continue
            try:
                category_id =  str(item['id']) + ProcessWavve.unique
                cls.vod_categories.append({'category_id' : category_id, 'category_name':item['title'], 'parent_id':0})
                if cls.is_working_time(item, mode) == False:
                    logger.debug('work no')
                    continue
                else:
                    cls.saved['vod'][category_id] = []
                page = 1
                category_count = 0
                while True:
                    vod_list = Wavve.movie_contents(page=page, genre=item['category'])
                    #logger.debug('Wavve vod genre : %s , page : %s', item['category'], page)
                    if vod_list is None or len(vod_list['list']) == 0:
                        break
                    # 이건 다 중복
                    id_type = 'vod_' + item['category']
                    for vod in vod_list['list']:
                        xc_id = ModelWavveMap.get_xc_id(id_type, vod['movieid'])
                        db_item = ModelWavveMap.get_by_xc_id(xc_id)
                        if db_item.program_data is None:
                            continue
                        if db_item.is_drm:
                            continue
                        if ModelSetting.get_bool('wavve_is_adult') == False and int(vod['targetage']) >= 18:
                            continue
                        entity = {
                            'name' : vod['title'],
                            "stream_type":"movie",
                            'stream_id' : xc_id,
                            'stream_icon' : 'https://' + vod['image'],
                            'rating' : vod['rating'],
                            'category_id' : category_id,
                            'is_adult' : '0',
                        }
                        #cls.vod_list.append(entity)
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
        logger.debug('WAVVE vod count : %s', len(cls.vod_list))

    @classmethod
    def make_series_data(cls, mode):
        #logger.debug('make_series_data')
        cls.series_categories = []
        cls.series_list = []
        timestamp = int(time.time())
        count = 0
        for item in cls.make_json(ModelSetting.get('wavve_series')):
            logger.debug('WAVVE series %s', item['title'])
            if ModelSetting.get_bool('wavve_is_adult') == False and 'is_adult' in item and item['is_adult']:
                continue
            category_id =  str(item['id']) + ProcessWavve.unique
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
                    if 'sub_category' not in item:
                        episode_list = Wavve.vod_contents(page=page, genre=item['category'])
                    else:
                        episode_list = Wavve.vod_allprograms(page=page, genre=item['category'], subgenre=item['sub_category'])
                    if episode_list is None or len(episode_list['list']) == 0:
                        break                  
                    for idx, episode in enumerate(episode_list['list']):
                        id_type = 'series_recent' if item['id'] == 1 else 'series'
                        id_type = id_type if item['category'] != '09' else 'series_foreign'
                        xc_id = ModelWavveMap.get_xc_id(id_type, episode['programid'])
                        db_item = ModelWavveMap.get_by_xc_id(xc_id)
                        if db_item.is_drm:
                            continue
                        if ModelSetting.get_bool('wavve_is_adult') == False and int(episode['targetage']) >= 18:
                            continue
                        entity = {
                            'name' : episode['programtitle'],
                            'series_id' : xc_id, 
                            'cover' : 'https://' + episode['image'],
                            'category_id' : category_id,
                            'last_modified' : timestamp - count
                        }
                        db_item = ModelWavveMap.get_by_xc_id(xc_id)
                        if db_item.program_data is not None:
                            entity['cover'] = 'https://' + db_item.program_data['posterimage']
                        # 여기서 이외정보는 넣어도 안씀.
                        #cls.series_list.append(entity)
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
                cls.vod_list += cls.saved['series'][category_id]
        logger.debug('WAVVE series count : %s', len(cls.series_list))



    @classmethod 
    def get_vod_info(cls, vod_id):
        try:
            db_item = ModelWavveMap.get_by_xc_id(vod_id)
            content_id = db_item.wavve_id
            program_data = db_item.program_data
            ret = {
                'info' : {
                    'plot' : program_data['synopsis'], 
                    'cast' : ', '.join([x['text'] for x in program_data['actors']['list']]),
                    'director' : ', '.join([x['text'] for x in program_data['directors']['list']]),
                    'genre' : ', '.join([x['text'] for x in program_data['genre']['list']]),
                    'releasedate' : program_data['releasedate'],
                    'duration_secs' : program_data['playtime'],
                },
                'movie_data' : {
                    'name' : program_data['title'],
                    "stream_type":"movie",
                    'stream_id' : vod_id,
                    'container_extension': 'mp4', # 이거 필수
                }
            }
            return ret
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())



    @classmethod 
    def get_series_info(cls, series_id):
        try:
            db_item = ModelWavveMap.get_by_xc_id(series_id)
            content_id = db_item.wavve_id
            program_data = db_item.program_data
            ret = {
                'seasons':[
                    {
                        'air-date' : program_data['firstreleasedate'] if program_data is not None and 'firstreleasedate' in program_data else '',
                        'name' : u'시즌 1',
                        'season_number' : 1,
                    }
                ],
                'info' : {
                    "name" : program_data['programtitle'], 
                    "cover" : 'https://' + program_data['posterimage'],
                    'plot' : program_data['programsynopsis'].replace('<br>', '\n'), 
                    'cast' : ', '.join([x['text'] for x in program_data['programactors']['list']]),
                    'genre' : ', '.join([x['text'] for x in program_data['tags']['list']]) + '   ' + program_data['channelname'],
                    'releasedate' : program_data['firstreleasedate'] 
                },
                'episodes': {'1' : []},
            }
            page = 1
            index = 1
            while True:
                episode_data = Wavve.vod_program_contents_programid(content_id, page=page)
                for episode in episode_data['list']:
                    item = {
                        "id" : ModelWavveMap.get_xc_id('episode', episode['contentid']),
                        "episode_num": episode['episodenumber'],
                        "title" : u'%s회 (%s)' % (episode['episodenumber'], episode['releasedate']) if episode['type'] == 'general' else u'QVOD %s회 (%s)' % (episode['episodenumber'], episode['releasedate']),
                        "container_extension": 'mp4',
                        "info": {
                            "movie_image" : 'https://' + episode['image'],
                            'duration_secs' : episode['playtime'],
                        },
                        "season": 1,
                    }
                    index += 1
                    ret['episodes']['1'].append(item)
                page += 1
                if episode_data['pagecount'] == episode_data['count'] or page == 6:
                    break
            return ret
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @classmethod 
    def get_streaming_url(cls, xc_id, content_type):
        content_id = ModelWavveMap.get_by_xc_id(xc_id).wavve_id
        if content_type == 'series':
            if content_id.startswith('PQV_'):
                content_type = 'onairvod'        
            else:
                content_type = 'vod'
        elif content_type == 'vod':
            content_type = 'movie'
        elif content_type == 'live':
            content_type = 'live'

        proxy = ModelSetting.get('wavve_proxy_url') if ModelSetting.get_bool('wavve_use_proxy') else None
        ret = Wavve.streaming(content_type, content_id, ModelSetting.get('wavve_quality'), ModelSetting.get('wavve_login_data'), proxy=proxy)
        return ret['playurl']


    @classmethod
    def get_channel_epg_data(cls, channelid):
        try:
            current_dt = datetime.now()
            start_param = current_dt.strftime('%Y-%m-%d') + ' 00:00'
            end_dt = current_dt + timedelta(days=1)
            end_param = end_dt.strftime('%Y-%m-%d') + ' 24:00'
            data = Wavve.live_epgs_channels(channelid, start_param, end_param)
            ret = []
            for item in data['list']:
                try:
                    entity = {}
                    entity['start_time'] = datetime.strptime(item['starttime'], '%Y-%m-%d %H:%M')
                    entity['end_time'] = datetime.strptime(item['endtime'], '%Y-%m-%d %H:%M')
                    entity['title'] = item['title']
                    ret.append(entity)
                except:
                    pass
            return ret
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())



class ModelWavveMap(db.Model):
    __tablename__ = '{package_name}_wavve_map'.format(package_name=P.package_name)
    __table_args__ = {'mysql_collate': 'utf8_general_ci'}
    __bind_key__ = P.package_name

    xc_id = db.Column(db.Integer, primary_key=True)
    wavve_id = db.Column(db.String, nullable=False)
    id_type = db.Column(db.String)
    program_data = db.Column(db.JSON)
    is_drm = db.Column(db.Boolean)
    
    def __init__(self, wavve_id, id_type):
        self.wavve_id = wavve_id
        self.id_type = id_type
        self.is_drm = False

    def as_dict(self):
        ret = {x.name: getattr(self, x.name) for x in self.__table__.columns}
        return ret

    @classmethod
    def get_xc_id(cls, id_type, wavve_id):
        item = db.session.query(cls).filter_by(wavve_id=wavve_id).filter_by(id_type=id_type).first()
        save_flag = False
        if item is None:
            item = ModelWavveMap(wavve_id, id_type)
            save_flag = True
        if id_type.startswith('series') and item.program_data is None:
            item.program_data = Wavve.vod_programs_programid(wavve_id)
            save_flag = True
            if id_type == 'series_foreign':
                contents = Wavve.vod_program_contents_programid(wavve_id)
                index = 0
                for idx, content in enumerate(contents['list']):
                    if content['price'] != '0':
                        index = idx
                        break
                content_data = Wavve.vod_contents_contentid(contents['list'][index]['contentid'])
                if content_data['drms'] != '':
                    #logger.debug(content_data['drms'])
                    item.is_drm = True
        if save_flag:
            db.session.add(item)
            db.session.commit()
        return str(item.xc_id) + ProcessWavve.unique
    
    @classmethod
    def get_by_xc_id(cls, xc_id):
        xc_id = int(xc_id[:-1])
        ret = db.session.query(cls).filter_by(xc_id=xc_id).first()
        if ret.id_type.startswith('vod') and ret.program_data is None:
            ret.program_data = Wavve.movie_contents_movieid(ret.wavve_id)
            if 'drm' in ret.program_data['moviemarks']:
                ret.is_drm = True
            db.session.add(ret)
            db.session.commit()
        return ret

wavve_default_live = u'''
[웨이브]\ncategory = all
#[웨이브 지상파]\n#category = 01
#[웨이브 종편/보도]\n#category = 02
#[웨이브 드라마/예능]\n#category = 04
#[웨이브 영화/스포츠]\n#category = 05
#[웨이브 키즈/애니]\n#category = 10
#[웨이브 라디오/음악]\n#category = 01
#[웨이브 홈쇼핑]\n#category = 03
#[웨이브 시사/교양]\n#category = 12
'''

wavve_default_vod = u'''
[웨이브]\ncategory = all\nmax_count = 100\nfrequency = 72
[웨이브 드라마]\ncategory = mgm01\nfrequency = 72
[웨이브 로맨스]\ncategory = mgm02\nfrequency = 72
[웨이브 코미디]\ncategory = mgm03\nfrequency = 72
[웨이브 액션]\ncategory = mgm04\nfrequency = 72
[웨이브 SF/판타지]\ncategory = mgm05\nfrequency = 72
[웨이브 모험]\ncategory = mgm06\nfrequency = 72
[웨이브 범죄]\ncategory = mgm07\nfrequency = 72
[웨이브 공포/스릴러]\ncategory = mgm08\nfrequency = 72
[웨이브 음악]\ncategory = mgm09\nfrequency = 72
[웨이브 애니메이션]\ncategory = mgm10\nfrequency = 72
[웨이브 다큐멘터리]\ncategory = mgm11\nfrequency = 72
[웨이브 전쟁/재난]\ncategory = mgm12\nfrequency = 72
[웨이브 가족]\ncategory = mgm15\nfrequency = 72
[웨이브 성인]\ncategory = mgm90\nfrequency = 72\nis_adult = true
[웨이브 성인+]\ncategory = mgm91\nfrequency = 72\nis_adult = true
'''

wavve_default_series = u'''
[웨이브 최근]\ncategory = all\nmax_count = 100\nfrequency = 1
[웨이브 드라마]\ncategory = 01\nmax_count = 100\nfrequency = 3
[웨이브 예능]\ncategory = 02\nmax_count = 100\nfrequency = 3
[웨이브 시사교양]\ncategory = 03\nmax_count = 100\nfrequency = 3
[웨이브 키즈]\ncategory = 06\nmax_count = 100\nfrequency = 6
[웨이브 스포츠]\ncategory = 05\nmax_count = 100\nfrequency = 6
[웨이브 애니메이션]\ncategory = 08\nmax_count = 100\nfrequency = 6
[웨이브 크리에이터]\ncategory = 12\nmax_count = 100\nfrequency = 6
[웨이브 해외시리즈]\ncategory = 09\nmax_count = 100\nfrequency = 72
[웨이브 해외-미국]\ncategory = 09\nsub_category = vsgm09001\nmax_count = 100\nfrequency = 72
[웨이브 해외-중국]\ncategory = 09\nsub_category = vsgm09002\nmax_count = 100\nfrequency = 72
[웨이브 해외-일본]\ncategory = 09\nsub_category = vsgm09004\nmax_count = 100\nfrequency = 72
[웨이브 해외-영국]\ncategory = 09\nsub_category = vsgm09003\nmax_count = 100\nfrequency = 72
[웨이브 해외-대만]\ncategory = 09\nsub_category = vsgm09016\nmax_count = 100\nfrequency = 72
'''