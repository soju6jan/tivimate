# -*- coding: utf-8 -*-
#########################################################
# python
import os, sys, traceback, re, json, threading, time, shutil
from datetime import datetime
# third-party
import requests
# third-party
from flask import request, render_template, jsonify, redirect
from sqlalchemy import or_, and_, func, not_, desc
import lxml.html
from lxml import etree as ET

# sjva 공용
from framework import db, scheduler, path_data, socketio, SystemModelSetting, app
from framework.util import Util
from framework.common.util import headers, get_json_with_auth_session
from framework.common.plugin import LogicModuleBase, default_route_socketio
# 패키지
from .plugin import P
logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting
#########################################################
from .process_plex import ProcessPlex, plex_default_vod, plex_default_series
from .process_wavve import ProcessWavve, wavve_default_live, wavve_default_vod, wavve_default_series
from .process_tving import ProcessTving, tving_default_live, tving_default_vod, tving_default_series

source_list = [ProcessPlex, ProcessWavve, ProcessTving]

@P.blueprint.route('/get.php', methods=['GET'])
def get_php():
    logger.debug('>> get.php : %s', request.args)
    return jsonify('')

@P.blueprint.route('/xmltv.php', methods=['GET'])
def xmltv_php():
    logger.debug('>> xmltv.php : %s', request.args)
    root = ET.Element('tv')
    root.set('generator-info-name', SystemModelSetting.get('ddns'))

    for source in source_list:
        tmp = source.get_live_channel_list()
        if tmp is None:
            continue
        for key, channel in tmp.items():
            channel_tag = ET.SubElement(root, 'channel') 
            channel_tag.set('id', '%s' % key)
            icon_tag = ET.SubElement(channel_tag, 'icon')
            icon_tag.set('src', channel['icon'])
            display_name_tag = ET.SubElement(channel_tag, 'display-name') 
            display_name_tag.text = channel['name']

            for program in channel['list']:
                program_tag = ET.SubElement(root, 'programme')
                program_tag.set('start', program['start_time'].strftime('%Y%m%d%H%M%S') + ' +0900')
                program_tag.set('stop', program['end_time'].strftime('%Y%m%d%H%M%S') + ' +0900')
                program_tag.set('channel', '%s' % key)
                title_tag = ET.SubElement(program_tag, 'title')
                title_tag.set('lang', 'ko')
                title_tag.text = program['title']
    return app.response_class(ET.tostring(root, pretty_print=True, xml_declaration=True, encoding="utf-8"), mimetype='application/xml')
   

@P.blueprint.route('/player_api.php')
def player_api_php():    
    logger.debug('>> player_api.php : %s', request.args)
    action = request.args.get('action')
    output = []
    index = 1
    if action == 'get_live_categories':
        for source in source_list:
            data = source.get_live_categories()
            if data is not None:
                output += data
    elif action == 'get_live_streams':
        for source in source_list:
            data = source.get_live_streams()
            if data is None or len(data) == 0:
                continue
            for item in data:
                entity = item
                entity['num'] = index
                index += 1
                output.append(entity)
    elif action == 'get_vod_categories':
        for source in source_list:
            data = source.get_vod_categories()
            if data is not None:
                output += data
    elif action == 'get_vod_streams':
        for source in source_list:
            data = source.get_vod_streams()
            if data is None or len(data) == 0:
                continue
            for item in data:
                entity = item
                entity['num'] = index
                index += 1
                output.append(entity)
    elif action == 'get_vod_info':
        vod_id = request.args.get('vod_id')
        output = source_list[int(vod_id)%10].get_vod_info(vod_id)
    elif action == 'get_series_categories':
        for source in source_list:
            data = source.get_series_categories()
            if data is not None:
                output += data
    elif action == 'get_series':
        for source in source_list:
            data = source.get_series()
            if data is None or len(data) == 0:
                continue
            for item in data:
                entity = item
                entity['num'] = index
                index += 1
                output.append(entity)
    elif request.args.get('action') == 'get_series_info':
        series_id = request.args.get('series_id')
        output = source_list[int(series_id[-1])].get_series_info(series_id)
    else:
        output = {"user_info":{"username":ModelSetting.get('user'),"password":ModelSetting.get('pass'),"message":"","auth":1,"status":"Active","exp_date":"1632734599","is_trial":"0","active_cons":"1","created_at":"1585304571","max_connections":"10","allowed_output_formats":["m3u8"]},"server_info":{"url":SystemModelSetting.get('ddns'),"port":"","https_port":"","server_protocol":"http","rtmp_port":"","timezone":"UTC","timestamp_now":int(time.time()),"time_now":datetime.now().strftime('%Y-%m-%d %H:%M:%S'),"process":True}}
   
    return jsonify(output)


def redirect_streaming_url(content_type, path):
    logger.debug('>> CONTENT : %s, PATH : %s, ags : %s', content_type, path, request.args)
    tmp = path.split('/')[-1].split('.')
    xc_id = tmp[0]
    url = source_list[int(xc_id)%10].get_streaming_url(xc_id, content_type)
    #if tmp[1] == 'strm':
    #    return url
    if content_type == 'vod' and (int(xc_id)%10) == 2:
        return url
    return redirect(url)

@P.blueprint.route('/movie/<path:path>')
def movie(path):
    return redirect_streaming_url('vod', path)

@P.blueprint.route('/series/<path:path>')
def series(path):
    return redirect_streaming_url('series', path)

@P.blueprint.route('/live/<path:path>')
def live(path):
    return redirect_streaming_url('live', path)


#@P.blueprint.route('/test.m3u')
#def mpd():
#    return "#EXTM3U\n#KODIPROP:inputstream.adaptive.license_type=com.widevine.alpha\n#KODIPROP:inputstream.adaptive.license_key=https://proxy.uat.widevine.com/proxy?provider=widevine_test\n#EXTINF:-1,Widevine encrypted\nhttps://storage.googleapis.com/wvmedia/cenc/h264/tears/tears.mpd"


class LogicXC(LogicModuleBase):
    db_default = {
        'db_version' : '1',
        'xc_auto_start' : 'False',
        'xc_interval' : '10',

        'use_auth' : 'False',
        'user' : 'user',
        'pass' : 'pass',
        'default_frequency' : '1',
        'default_max_count' : '20',

        'plex_use' : 'False',
        'plex_server' : '',
        'plex_token' : '',
        'plex_vod' : plex_default_vod,
        'plex_series' : plex_default_series,
        'plex_all_container' : 'False',

        'wavve_use' : 'True',
        'wavve_login_data' : '', 
        'wavve_use_proxy' : 'False', 
        'wavve_proxy_url' : '', 
        'wavve_quality' : 'HD', 
        'wavve_is_adult' : 'False', 
        'wavve_live' : wavve_default_live, 
        'wavve_vod' : wavve_default_vod, 
        'wavve_series' : wavve_default_series, 

        'tving_use' : 'True',
        'tving_login_data' : '', 
        'tving_use_proxy' : 'False', 
        'tving_proxy_url' : '', 
        'tving_quality' : 'HD', 
        'tving_is_adult' : 'False', 
        'tving_live' : tving_default_live, 
        'tving_vod' : tving_default_vod, 
        'tving_series' : tving_default_series, 
    }

    def __init__(self, P):
        super(LogicXC, self).__init__(P, 'base', scheduler_desc=u'tivimate 항목 생성')
        self.name = 'xc'

    def process_menu(self, sub, req):
        arg = P.ModelSetting.to_dict()
        arg['sub'] = self.name
        if sub in ['base']:
            job_id = '%s_%s' % (self.P.package_name, self.name)
            arg['scheduler'] = str(scheduler.is_include(job_id))
            arg['is_running'] = str(scheduler.is_running(job_id))
            arg['scheduler_count'] = u'%s 회 실행' % P.scheduler_count
            arg['tivimate_url'] = '{}/{}'.format(SystemModelSetting.get('ddns'), P.package_name)
            return render_template('{package_name}_{module_name}_{sub}.html'.format(package_name=P.package_name, module_name=self.name, sub=sub), arg=arg)
        return render_template('sample.html', title='%s - %s' % (P.package_name, sub))

    def process_ajax(self, sub, req):
        try:
            if sub == 'all_load':
                def func():
                    ProcessPlex.scheduler_function(mode='force')
                    ProcessWavve.scheduler_function(mode='force')
                    ProcessTving.scheduler_function(mode='force')
                    socketio.emit("notify", data = {'type':'success', 'msg' : u'<strong>아이템 로딩 완료</strong>'}, namespace='/framework', broadcast=True)    
                t = threading.Thread(target=func, args=())
                t.daemon = True
                t.start()
                return jsonify(True)
        except Exception as e: 
            P.logger.error('Exception:%s', e)
            P.logger.error(traceback.format_exc())
            return jsonify({'ret':'exception', 'log':str(e)})

    #########################################################

    
    def scheduler_function(self):
        try:
            mode = 'force' if (P.scheduler_count % 50) == 0 else 'scheduler'
            ProcessPlex.scheduler_function(mode=mode)
            ProcessWavve.scheduler_function(mode=mode)
            ProcessTving.scheduler_function(mode=mode)
            logger.debug('scheduler_function end..')
        except Exception as e: 
            P.logger.error('Exception:%s', e)
            P.logger.error(traceback.format_exc())
        finally:
            P.scheduler_count += 1
    
