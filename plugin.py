# -*- coding: utf-8 -*-
# python
import os, traceback
# third-party
from flask import Blueprint
# sjva 공용
from framework.logger import get_logger
from framework import app, path_data
from framework.util import Util
from plugin import get_model_setting, Logic, default_route, PluginUtil
# 패키지
#########################################################
class P(object):
    package_name = __name__.split('.')[0]
    logger = get_logger(package_name)
    blueprint = Blueprint(package_name, package_name, url_prefix='/%s' %  package_name, template_folder=os.path.join(os.path.dirname(__file__), 'templates'))
    menu = {
        'main' : [package_name, u'TiviMate 연동'],
        'sub' : [
            ['xc', u'Xstream Code 설정'], ['log', u'로그']
        ], 
        'category' : 'tv',
        'sub2' : {
            'xc' : [
                ['base', u'기본'],
            ],
        }
    }  

    plugin_info = {
        'version' : '0.2.0.0',
        'name' : 'tivimate',
        'category_name' : 'tv',
        'icon' : '',
        'developer' : u'soju6jan',
        'description' : u'Xstream codes 서버. tivimate 연동.',
        'home' : 'https://github.com/soju6jan/tivimate',
        'more' : '',
    }
    ModelSetting = get_model_setting(package_name, logger)
    logic = None
    module_list = None
    home_module = 'xc'

    scheduler_count = 0

def initialize():
    try:
        app.config['SQLALCHEMY_BINDS'][P.package_name] = 'sqlite:///%s' % (os.path.join(path_data, 'db', '{package_name}.db'.format(package_name=P.package_name)))
        PluginUtil.make_info_json(P.plugin_info, __file__)

        from .logic_xc import LogicXC
        P.module_list = [LogicXC(P)]
        P.logic = Logic(P)
        default_route(P)
    except Exception as e: 
        P.logger.error('Exception:%s', e)
        P.logger.error(traceback.format_exc())

initialize()

