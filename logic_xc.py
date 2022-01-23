# -*- coding: utf-8 -*-
#########################################################
# python
import os, sys, traceback, re, json, threading, time, shutil
from datetime import datetime
import urllib
# third-party
import requests
# third-party
from flask import request, render_template, jsonify, redirect, send_file
from sqlalchemy import or_, and_, func, not_, desc
import lxml.html
from lxml import etree as ET

# sjva 공용
from framework import db, scheduler, path_data, socketio, SystemModelSetting, app
from framework.util import Util
from framework.common.util import headers
from plugin import LogicModuleBase, default_route_socketio
# 패키지
from .plugin import P
logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting
#########################################################
from .process_plex import ProcessPlex, plex_default_vod, plex_default_series
from .process_wavve import ProcessWavve, wavve_default_live, wavve_default_vod, wavve_default_series
from .process_tving import ProcessTving, tving_default_live, tving_default_vod, tving_default_series
from .process_sstv import ProcessSstv
from .process_spotv import ProcessSpotv

source_list = [ProcessPlex, ProcessWavve, ProcessTving, ProcessSpotv, ProcessSstv]

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
                if 'desc' in program:
                    desc_tag = ET.SubElement(program_tag, 'desc')
                    desc_tag.text = program['desc']
                if 'icon' in program:
                    icon_tag = ET.SubElement(program_tag, 'icon')
                    icon_tag.set('src', program['icon'])

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
            data = source.get_live_streams(category_id=request.args.get('category_id'))
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
            data = source.get_vod_streams(category_id=request.args.get('category_id'))
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
            data = source.get_series(category_id=request.args.get('category_id'))
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
    #logger.debug('>> CONTENT : %s, PATH : %s, ags : %s', content_type, path, request.args)
    tmp = path.split('/')[-1].split('.')
    xc_id = tmp[0]
    url = source_list[int(xc_id)%10].get_streaming_url(xc_id, content_type, extension=tmp[1])
    if type(url) == type({}):
        return jsonify(url)
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


@P.blueprint.route('/img', methods=['GET', 'POST'])
def img():
    from PIL import Image
    image_url = urllib.parse.unquote_plus(request.args.get('url'))
    im = Image.open(requests.get(image_url, stream=True).raw)
    width, height = im.size
    new_height = height
    new_width = int(height * 1.78)
    #new_image = Image.new('RGBA',(new_width, new_height), (0,0,0, 0))
    new_image = Image.new('RGBA',(new_width, new_height), (0,0,0,0))
    new_image.paste(im, (int((new_width - width)/2), 0))
    filename = os.path.join(path_data, 'tmp', f'proxy_{str(time.time())}.png')
    new_image.save(filename)
    #return send_file(filename, mimetype='image/jpeg')
    return send_file(filename, mimetype='image/png')


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
        'drm_include' : 'False',
        'drm_notify' : 'True',

        'plex_use' : 'False',
        'plex_server' : '',
        'plex_token' : '',
        'plex_vod' : plex_default_vod,
        'plex_series' : plex_default_series,
        'plex_all_container' : 'False',

        'wavve_use' : 'True',
        'wavve_quality' : 'HD', 
        'wavve_is_adult' : 'False', 
        'wavve_live' : wavve_default_live, 
        'wavve_vod' : wavve_default_vod, 
        'wavve_series' : wavve_default_series, 

        'tving_use' : 'True',
        'tving_quality' : 'HD', 
        'tving_is_adult' : 'False', 
        'tving_live' : tving_default_live, 
        'tving_vod' : tving_default_vod, 
        'tving_series' : tving_default_series, 

        'sstv_use' : 'True',
        'sstv_only_kor' : 'True',
        'sstv_group_only_country' : 'True',
    
        'spotv_use' : 'False',
        'spotv_pk' : '',
        'spotv_username' : '',
        'spotv_password' : '',
        'spotv_quality' : '',
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
                    ProcessSstv.scheduler_function(mode='force')
                    ProcessSpotv.scheduler_function(mode='force')
                    ProcessWavve.scheduler_function(mode='force')
                    ProcessTving.scheduler_function(mode='force')
                    ProcessPlex.scheduler_function(mode='force')
                    socketio.emit("notify", data = {'type':'success', 'msg' : u'<strong>아이템 로딩 완료</strong>'}, namespace='/framework', broadcast=True)    
                t = threading.Thread(target=func, args=())
                t.daemon = True
                t.start()
                return jsonify(True)
        except Exception as e: 
            P.logger.error('Exception:%s', e)
            P.logger.error(traceback.format_exc())
            return jsonify({'ret':'exception', 'log':str(e)})

    def reset_db(self):
        from .process_wavve import ModelWavveMap
        db.session.query(ModelWavveMap).delete()
        from .process_tving import ModelTvingMap
        db.session.query(ModelTvingMap).delete()
        db.session.commit()
        return True
        

    #########################################################

    
    def scheduler_function(self):
        try:
            mode = 'force' if (P.scheduler_count % 50) == 0 else 'scheduler'
            ProcessSstv.scheduler_function(mode=mode)
            ProcessSpotv.scheduler_function(mode=mode)
            ProcessWavve.scheduler_function(mode=mode)
            ProcessTving.scheduler_function(mode=mode)
            ProcessPlex.scheduler_function(mode=mode)
            logger.debug('scheduler_function end..')
        except Exception as e: 
            P.logger.error('Exception:%s', e)
            P.logger.error(traceback.format_exc())
        finally:
            P.scheduler_count += 1
    
