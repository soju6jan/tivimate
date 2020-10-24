# -*- coding: utf-8 -*-
from .plugin import P
ModelSetting = P.ModelSetting

class ProcessBase(object):
    live_categories = None
    live_list = None
    live_channel_list = None
    vod_categories = None
    vod_list = None
    series_categories = None
    series_list = None

    @classmethod 
    def plugin_load(cls):
        pass

    @classmethod 
    def get_live_categories(cls):
        return cls.live_categories

    @classmethod 
    def get_live_streams(cls):
        return cls.live_list

    @classmethod 
    def get_live_channel_list(cls):
        return cls.live_channel_list

    @classmethod 
    def get_vod_categories(cls):
        return cls.vod_categories

    @classmethod 
    def get_vod_streams(cls):
        return cls.vod_list

    @classmethod 
    def get_vod_info(cls, vod_id):
        pass

    @classmethod 
    def get_series_categories(cls):
        return cls.series_categories

    @classmethod 
    def get_series(cls):
        return cls.series_list

    @classmethod 
    def get_series_info(cls, series_id):
        pass

    @classmethod 
    def get_streaming_url(cls, xc_id, content_type):
        pass

    @classmethod 
    def make_json(cls, data):
        try:
            tmp = data.split('\n')
            ret = []
            entity = None
            for line in tmp:
                line = line.split('#')[0].strip()
                key_value = line.split('=')
                if line == '':
                    continue
                elif line.startswith('['):
                    if entity is not None:
                        entity['id'] = len(ret) + 1
                        entity['max_count'] = entity['max_count'] if 'max_count' in entity else ModelSetting.get_int('default_max_count')
                        ret.append(entity)
                    entity = {}
                    entity['title'] = line.split('[')[1].split(']')[0].strip()
                elif len(key_value) == 2:
                    key = key_value[0].strip()
                    value = key_value[1].strip()
                    if key in ['max_count', 'frequency']:
                        entity[key] = int(value)
                    else:
                        if value.lower() == 'true':
                            value = True
                        elif value.lower() == 'false':
                            value = False
                        entity[key] = value
            if entity is not None:
                entity['id'] = len(ret) + 1
                entity['max_count'] = entity['max_count'] if 'max_count' in entity else ModelSetting.get_int('default_max_count')
                ret.append(entity)
            return ret
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @classmethod 
    def is_working_time(cls, item, mode):
        try:
            if P.scheduler_count == 0:
                return True
            if mode == 'force':
                return True
            frequency = item['frequency'] if 'freqeuncy' in item else ModelSetting.get_int('default_freqeuncy')
            if mode == 'scheduler':
                if frequency == 0:
                    return False
                else:
                    return ((P.scheduler_count % freqeuncy) == 0)
        except Exception as e:
            P.logger.error('Exception:%s', e)
            P.logger.error(traceback.format_exc())
        return True    
    