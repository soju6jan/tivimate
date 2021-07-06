# -*- coding: utf-8 -*-
#########################################################
# python
import os, sys, traceback, re, json, threading, time, shutil, gzip
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


DATA_URL = 'https://i.mjh.nz/SamsungTVPlus/app.json.gz'
EPG_URL = 'https://i.mjh.nz/SamsungTVPlus/all.xml.gz'


class ProcessSstv(ProcessBase):
    unique = '3'
    data = None

    @classmethod 
    def scheduler_function(cls, mode='scheduler'):
        try:
            if ModelSetting.get_bool('sstv_use') == False:
                return
            cls.make_live_data(mode)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())



    @classmethod
    def make_live_data(cls, mode):
        cls.live_categories = []
        cls.live_list = []
        cls.live_channel_list = OrderedDict()
        
        cls.data = cls.get_data()

        
        #for item in cls.make_json(ModelSetting.get('tving_live')):
        group_list = []
        for index, item in enumerate(cls.data):
            try:
                if ModelSetting.get_bool(f'sstv_only_kor'):
                    group_name = item["group"]
                elif ModelSetting.get_bool(f'sstv_group_only_country'):
                    group_name = item["country"]
                else:
                    group_name = f'{item["country"]} {item["group"]}'

                current_category = None
                for category in cls.live_categories:
                    if category['category_name'] == group_name:
                        current_category = category
                        break
                if current_category is None:
                    current_category = {'category_id' : str(len(cls.live_categories)+1) + ProcessSstv.unique, 'category_name':group_name, 'parent_id':0}
                    cls.live_categories.append(current_category)


                entity = {
                    'name' : item['name'],
                    "stream_type":"live",
                    "stream_id":"live",
                    'stream_id' : str(item['chno']) + ProcessSstv.unique,
                    'stream_icon' : item['logo'],
                    "epg_channel_id" : item['channel'],
                    "added":"1492282762",
                    "is_adult":"0",
                    "category_id":current_category['category_id'],
                    "custom_sid":"",
                    "tv_archive":0,
                    "direct_source":"",
                    "tv_archive_duration":0
                }
                cls.live_list.append(entity)
                cls.live_channel_list[item['channel']] = {'name':entity['name'], 'icon':entity['stream_icon'], 'list':[]}
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())

        #logger.warning(cls.live_categories)   
        logger.debug('sstv live count : %s', len(cls.live_list))
        cls.make_channel_epg_data()


    @classmethod
    def get_data(cls):
        data = json.loads(gzip.decompress(requests.get(DATA_URL).content))['regions']
        regions = [('kr', '한국'), ('us', '미국'), ('gb', '영국'), ('in', '인도'), ('de', '독일'), ('it', '이탈리아'), ('es', '스페인'), ('fr', '프랑스'), ('fr', '프랑스'), ('ch', '스위스'), ('at', '오스트리아')]
        if ModelSetting.get_bool('sstv_only_kor'):
            regions = [regions[0]]
        ret = []
        for code, country in regions:
            for channel, value in data[code]['channels'].items():
                value['channel'] = channel
                value['country'] = country
                ret.append(value)
        return ret
   

    @classmethod 
    def get_streaming_url(cls, xc_id, content_type, extension="m3u8"):
        
        xc_id = int(xc_id[:-1])
        logger.warning(xc_id)
        if content_type == 'live':
            if cls.data is None:
                cls.data = cls.get_data()
            for item in cls.data:
                #logger.warning(item['chno'])
                if item['chno'] == xc_id:
                    return item['url']
            
        







    @classmethod
    def make_channel_epg_data(cls):
        try:

            data = gzip.decompress(requests.get(EPG_URL).content)
            root = ET.fromstring(data)

            item_list = root.findall('programme')
            logger.debug('xml item count:%s', len(item_list))
            ret = []
            for item in item_list:
                try:
                    if item.attrib['channel'] not in cls.live_channel_list:
                        continue
                    start = item.attrib['start'].split(' ')[0]
                    stop = item.attrib['stop'].split(' ')[0]
                    entity = {}
                    entity['start_time'] = datetime.strptime(start, '%Y%m%d%H%M%S') + timedelta(hours=9)
                    entity['end_time'] = datetime.strptime(stop, '%Y%m%d%H%M%S') + timedelta(hours=9)
                    entity['title'] = item.find('title').text.strip()
                    entity['desc'] = item.find('desc').text.strip()
                    entity['icon'] = item.find('icon').attrib['src']
                    cls.live_channel_list[item.attrib['channel']]['list'].append(entity)
                except Exception as exception:
                    logger.debug(exception)
                    logger.debug(traceback.format_exc())
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

