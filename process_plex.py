# -*- coding: utf-8 -*-
#########################################################
# python
import os, sys, traceback, re, json, threading, time, shutil
from datetime import datetime
from collections import OrderedDict
# third-party
import requests
# third-party
from flask import request, render_template, jsonify, redirect
from sqlalchemy import or_, and_, func, not_, desc
import lxml.html
from lxml import etree as ET
import lxml

# sjva 공용
from framework import db, scheduler, path_data, socketio, SystemModelSetting, py_urllib2
from framework.util import Util

# 패키지
from .plugin import P
from .process_base import ProcessBase
logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting
#########################################################

plex_default_vod = u'''
[PLEX 최신]
section = recent
max_count = 100
frequency = 6

#[PLEX 영화]
#section = 22
#frequency = 30
'''

plex_default_series = u'''
[PLEX 최신]
section = recent
max_count = 100
frequency = 1

#[PLEX 드라마]
#section = 45
#max_count = 50
#frequency = 2
'''


class ProcessPlex(ProcessBase):
    unique = '0'
    saved = {'vod':{}, 'series':{}}
    @classmethod 
    def scheduler_function(cls, mode='scheduler'):
        #logger.debug(ModelSetting.get('plex_vod'))
        if ModelSetting.get_bool('plex_use') == False:
            return
        rule = {'vod' : cls.make_json(ModelSetting.get('plex_vod')), 'series':cls.make_json(ModelSetting.get('plex_series'))}
        timestamp = int(time.time())
        for content_type in ['vod', 'series']:
            if rule[content_type] is None or len(rule[content_type]) == 0:
                continue
            content_categories = []
            content_list = []
            
            for item in rule[content_type]:
                logger.debug('PLEX %s %s', content_type, item['title'])
                #max_count = item['max_count'] if 'max_count' in item else ModelSetting.get_int('default_max_count')
                count = 0
                try:
                    category_id =  str(item['id']) + ProcessPlex.unique
                    content_categories.append({'category_id' : category_id, 'category_name':item['title'], 'parent_id':0})
                    if cls.is_working_time(item, mode) == False:
                        logger.debug('work no')
                        continue
                    else:
                        cls.saved[content_type][category_id] = []
                    plex_content = '1' if content_type == 'vod' else '2'
                    if item['section'] == 'recent':
                        url = '{}/hubs/home/recentlyAdded?type={}&X-Plex-Token={}'.format(ModelSetting.get('plex_server'), plex_content, ModelSetting.get('plex_token'))
                    else:
                        url = '{}/library/sections/{}/all?type={}&sort=addedAt:desc&X-Plex-Container-Start=0&X-Plex-Container-Size={}&X-Plex-Token={}'.format(ModelSetting.get('plex_server'), item['section'], plex_content, item['max_count'], ModelSetting.get('plex_token'))

                    logger.debug(url)
                    doc = lxml.html.parse(py_urllib2.urlopen(url, timeout=30))
                    
                    videos = doc.xpath("//video")
                    if len(videos) == 0:
                        videos = doc.xpath("//directory")

                    for tag_video in videos:
                        logger.debug('count : %s - %s', count, tag_video.attrib['title'].replace('  ', ' '))
                        if tag_video.attrib['type'] in ['movie', 'episode']:
                            tmp = tag_video.xpath('.//media')
                            if tmp:
                                tag_media = tmp[0]
                            else:
                                continue
                        
                        if tag_video.attrib['type'] == 'movie':
                            # mp4만
                            tag_part = tag_media.xpath('.//part')[0]
                            if 'container' not in tag_part.attrib:
                                continue
                            container = tag_part.attrib['container']
                            if ModelSetting.get_bool('plex_all_container') == False and  container != 'mp4':
                                continue

                            #if 'container' not in tag_part.attrib or tag_part.attrib['container'] != 'mp4':
                            #    continue
                            
                            xc_id = ModelPlexMap.get_xc_id(content_type + '_%s' % item['section'], tag_video.attrib['ratingkey'])
                            entity = {
                                'name' : tag_video.attrib['title'].replace('  ', ' '),
                                "stream_type":"movie",
                                'stream_id' : xc_id,
                                'stream_icon' : '%s%s?X-Plex-Token=%s' % (ModelSetting.get('plex_server'), tag_video.attrib['thumb'], ModelSetting.get('plex_token')),
                                'category_id' : category_id,
                                'is_adult' : '0',
                            }
                            db_item = ModelPlexMap.get_by_xc_id(xc_id)
                            if db_item.program_data is None:
                                db_item.set_data({
                                    'vod_info' : {
                                        'info' : {
                                            'plot' : '%s' % tag_video.attrib['summary'] if tag_video.attrib['summary'] !='' else '\n', 
                                            'cast' : ', '.join([x.attrib['tag'] for x in tag_video.xpath('.//role')]).rstrip(','), 
                                            'director' : ', '.join([x.attrib['tag'] for x in tag_video.xpath('.//director')]).rstrip(','), 
                                            'genre' : ', '.join([x.attrib['tag'] for x in tag_video.xpath('.//genre')]).rstrip(','), 
                                            'releasedate' : tag_video.attrib['originallyavailableat'] if 'originallyavailableat' in tag_video.attrib else '1900-01-01',
                                            'duration_secs' : int(tag_media.attrib['duration'])/1000,

                                            #https://192-168-0-68.32f6e98680924c50b0d69534fa212e71.plex.direct:32400/library/streams/1709672?encoding=utf-8&format=srt&X-Plex-Token=y639N-_xzchLS3ev2pjJ
                                        },
                                        'movie_data' : {
                                            'name' : entity['name'],
                                            "stream_type":"movie",
                                            'stream_id' : entity['stream_id'],
                                            'container_extension': container,
                                        }
                                    },
                                })
                        elif tag_video.attrib['type'] == 'episode' or tag_video.attrib['type'] == 'show':
                            ratingkey_tag = 'grandparentratingkey' if tag_video.attrib['type'] == 'episode' else 'ratingkey'
                            title_tag = 'grandparenttitle' if tag_video.attrib['type'] == 'episode' else 'title'
                            thumb_tag = 'grandparentthumb' if tag_video.attrib['type'] == 'episode' else 'thumb'
                            xc_id = ModelPlexMap.get_xc_id(content_type + '_%s' % item['section'], tag_video.attrib[ratingkey_tag])
                            entity = {
                                'name' : tag_video.attrib[title_tag].replace('  ', ' '),
                                'series_id' : xc_id,
                                'cover' : '%s%s?X-Plex-Token=%s' % (ModelSetting.get('plex_server'), tag_video.attrib[thumb_tag], ModelSetting.get('plex_token')) if thumb_tag in tag_video.attrib else '',
                                'category_id' : category_id,
                                'last_modified' : timestamp - count
                            }
                            db_item = ModelPlexMap.get_by_xc_id(xc_id)
                            if db_item.program_data is None:
                                db_item.set_data({
                                    'info' : {
                                        "name" : entity['name'], 
                                        "cover" : entity['cover'],
                                        'plot' : '%s' % tag_video.attrib['summary'] if tag_video.attrib['summary'] !='' else '\n', 
                                        'cast' : ', '.join([x.attrib['tag'] for x in tag_video.xpath('.//role')]), 
                                        'director' : ', '.join([x.attrib['tag'] for x in tag_video.xpath('.//director')]), 
                                        'genre' : ', '.join([x.attrib['tag'] for x in tag_video.xpath('.//genre')]), 
                                        'releasedate' : tag_video.attrib['originallyavailableat'] if 'originallyavailableat' in tag_video.attrib else '',
                                    }
                                })
                        else:
                            #tag_video.attrib['type'] == 'clip':
                            continue
                        #content_list.append(entity)
                        cls.saved[content_type][category_id].append(entity)
                        count += 1
                        if count >= item['max_count']:
                            break 
                except Exception as e:
                    logger.error('Exception:%s', e)
                    logger.error(traceback.format_exc())
                finally:
                    logger.debug('append : %s', len(cls.saved[content_type][category_id]))
                    content_list += cls.saved[content_type][category_id]
            if content_type == 'vod':
                cls.vod_categories = content_categories
                cls.vod_list = content_list
            else:
                cls.series_categories = content_categories
                cls.series_list = content_list
            

    @classmethod 
    def get_vod_info(cls, vod_id):
        try:
            db_item = ModelPlexMap.get_by_xc_id(vod_id)
            logger.debug(db_item.plex_id)
            logger.debug(db_item.program_data)
            
            url = '{}/library/metadata/{}?X-Plex-Token={}'.format(ModelSetting.get('plex_server'), db_item.plex_id, ModelSetting.get('plex_token'))
            logger.debug(url)
            doc = lxml.html.parse(py_urllib2.urlopen(url))
            streams = doc.xpath("//part/stream")
            subtitles = []
            for stream in streams:
                if stream.attrib['streamtype'] == '3' and 'key' in stream.attrib:
                    logger.debug(stream.attrib['key'])
                    subtitle_url = '{}{}?X-Plex-Token={}&encoding=utf-8'.format(ModelSetting.get('plex_server'), stream.attrib['key'], ModelSetting.get('plex_token'))
                    if stream.attrib['codec'] == 'smi':
                        subtitle_url += "&format=srt"
                    subtitles.append({'url':subtitle_url, 'language': stream.attrib['languagecode'] if 'languagecode' in stream.attrib else '', 'format' : stream.attrib['format']})
                    # https://github.com/plexinc/plex-for-kodi/blob/e6610e42ce1afd115cf59632b949e18597625323/lib/_included_packages/plexnet/plexstream.py#L106
            ret = db_item.program_data['vod_info']
            if subtitles:
                ret['info']['subtitles'] = subtitles
            return ret
            #return db_item.program_data['vod_info']
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
      


    @classmethod 
    def get_series_info(cls, series_id):
        try:
            db_item = ModelPlexMap.get_by_xc_id(series_id)
            content_id = db_item.plex_id
            program_data = db_item.program_data

            url = '{}/library/metadata/{}/allLeaves?X-Plex-Token={}'.format(ModelSetting.get('plex_server'), db_item.plex_id, ModelSetting.get('plex_token'))

            doc = lxml.html.parse(py_urllib2.urlopen(url))
            videos = doc.xpath("//video")
            
            ret = {'seasons':[], 'info':db_item.program_data['info'], 'episodes':{}}

            logger.debug(url)

            season_list = []
            for tag_video in list(reversed(videos)):
                tmp = tag_video.xpath('.//media')
                if tmp:
                    tag_media = tmp[0]
                else:
                    continue
                tag_part = tag_media.xpath('.//part')[0]
                if 'container' not in tag_part.attrib:
                    continue
                container = tag_part.attrib['container']
                if ModelSetting.get_bool('plex_all_container') == False and  container != 'mp4':
                    continue
                xc_id = ModelPlexMap.get_xc_id('episode', tag_video.attrib['ratingkey'])
                #episode_db_item = ModelPlexMap.get_by_xc_id(xc_id)
                episode_entity = {
                    "id" : xc_id,
                    "episode_num": tag_video.attrib['index'] if 'index' in tag_video.attrib else tag_video.attrib['originallyavailableat'],
                    "title" : u'%s회 (%s)' % (tag_video.attrib['index'] if 'index' in tag_video.attrib else '', tag_video.attrib['originallyavailableat'] if 'originallyavailableat' in tag_video.attrib else ''),
                    "container_extension": container,
                    "info": {
                        "movie_image" : '%s%s?X-Plex-Token=%s' % (ModelSetting.get('plex_server'), tag_video.attrib['thumb'], ModelSetting.get('plex_token')),
                    },
                    "season": tag_video.attrib['parentindex'],
                }
                if episode_entity['season'] not in season_list:
                    season_list.append([tag_video.attrib['parenttitle'], episode_entity['season'], ])

                if episode_entity['season'] not in ret['episodes']:
                    ret['episodes'][episode_entity['season']] = []
                
                ret['episodes'][episode_entity['season']].append(episode_entity)


            for tmp in list(reversed(season_list)):
                ret['seasons'].append({
                    'air-date' : '',
                    'name' : tmp[0],
                    'season_number' : tmp[1],
                })
            #logger.debug(ret)
            return ret
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())



    @classmethod 
    def get_streaming_url(cls, xc_id, content_type, extension="m3u8"):
        db_item = ModelPlexMap.get_by_xc_id(xc_id)
        #if content_type == 'vod':
        #    return db_item.program_data['streaming_url']

        url = '{}/library/metadata/{}?X-Plex-Token={}'.format(ModelSetting.get('plex_server'), db_item.plex_id, ModelSetting.get('plex_token'))
        
        doc = lxml.html.parse(py_urllib2.urlopen(url))
        tag = doc.xpath("//video/media/part")[0]
        

        return '%s%s?X-Plex-Token=%s&dummy=/series/' % (ModelSetting.get('plex_server'), tag.attrib['key'], ModelSetting.get('plex_token'))



class ModelPlexMap(db.Model):
    __tablename__ = '{package_name}_plex_map'.format(package_name=P.package_name)
    __table_args__ = {'mysql_collate': 'utf8_general_ci'}
    __bind_key__ = P.package_name

    xc_id = db.Column(db.Integer, primary_key=True)
    plex_id = db.Column(db.String, nullable=False)
    id_type = db.Column(db.String)
    program_data = db.Column(db.JSON)
    is_drm = db.Column(db.Boolean)
    
    def __init__(self, plex_id, id_type):
        self.plex_id = plex_id
        self.id_type = id_type
        self.is_drm = False

    def as_dict(self):
        ret = {x.name: getattr(self, x.name) for x in self.__table__.columns}
        return ret

    @classmethod
    def get_xc_id(cls, id_type, plex_id):
        item = db.session.query(cls).filter_by(plex_id=plex_id).filter_by(id_type=id_type).first()
        save_flag = False
        if item is None:
            item = ModelPlexMap(plex_id, id_type)
            save_flag = True
        if save_flag:
            db.session.add(item)
            db.session.commit()
        return str(item.xc_id) + ProcessPlex.unique
    
    @classmethod
    def get_by_xc_id(cls, xc_id):
        xc_id = int(xc_id[:-1])
        ret = db.session.query(cls).filter_by(xc_id=xc_id).first()
        return ret

    def set_data(self, data):
        self.program_data = data
        db.session.add(self)
        db.session.commit()