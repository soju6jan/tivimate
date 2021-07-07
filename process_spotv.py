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
from tool_base import d

# 패키지
from .plugin import P
from .process_base import ProcessBase
logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting
#########################################################


class ProcessSpotv(ProcessBase):
    unique = '3'
    data = None

    @classmethod 
    def scheduler_function(cls, mode='scheduler'):
        try:
            if ModelSetting.get_bool('spotv_use') == False:
                return
            cls.make_live_data(mode)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @classmethod
    def make_live_data(cls, mode):
        cls.live_categories = [{'category_id' : '1' + ProcessSpotv.unique, 'category_name':'Spotv', 'parent_id':0}]
        cls.live_list = []
        cls.live_channel_list = OrderedDict()
        cls.data = cls.get_broad_list()
        for index, item in enumerate(cls.data):
            try:
                entity = {
                    'name' : item[0],
                    "stream_type":"live",
                    "stream_id":"live",
                    'stream_id' : str(index+1) + ProcessSpotv.unique,
                    'stream_icon' : '',
                    "epg_channel_id" : item[1],
                    "added":"1492282762",
                    "is_adult":"0",
                    "category_id":'1' + ProcessSpotv.unique,
                    "custom_sid":"",
                    "tv_archive":0,
                    "direct_source":"",
                    "tv_archive_duration":0
                }
                cls.live_list.append(entity)
                cls.live_channel_list[item[1]] = {'name':entity['name'], 'icon':entity['stream_icon'], 'list':[]}
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        logger.debug('spotv live count : %s', len(cls.live_list))
        #cls.make_channel_epg_data()

    @classmethod
    def get_broad_list(cls):
        fix_list = []
        session = requests.post('https://www.spotvnow.co.kr/api/v2/login', json={"username":ModelSetting.get('spotv_username'),"password":ModelSetting.get('spotv_password')}).cookies['SESSION']
        data = requests.get(f"https://www.spotvnow.co.kr/api/v2/player/lives/{datetime.now().strftime('%Y-%m-%d')}", headers={'Cookie':f'SESSION={session}'}).json()
        for league in data: 
            for game in league['liveNowList']:
                fix_list.append([f"{league['name']} - {game['gameDesc']['title']}" if game['gameDesc']['title']  else f"{league['name']} - {game['gameDesc']['awayName']} vs {game['gameDesc']['homeName']}", requests.get(f"https://www.spotvnow.co.kr/api/v2/live/{game['liveId']}", headers={'Cookie':f'SESSION={session}'}).json()['videoId'].split(':')[1]])
        return fix_list
   

    @classmethod 
    def get_streaming_url(cls, xc_id, content_type, extension="m3u8"):
        xc_id = int(xc_id[:-1]) - 1
        if cls.data is None:
            cls.data = cls.get_broad_list()
        ch = cls.data[xc_id][1]
        return requests.get(f"https://edge.api.brightcove.com/playback/v1/accounts/5764318566001/videos/ref%3A{ch}", headers={'Accept':f"application/json;pk={ModelSetting.get('spotv_pk')}"}).json()['sources'][0]['src']


