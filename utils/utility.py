import configparser
from jinja2 import Environment, FileSystemLoader


def read_file(filename):
    with open(filename, 'r') as myfile:
        data=myfile.read().replace('\n', '')
    return data

def generate_ffserver_conf(filename,channels):
    env = Environment(loader=FileSystemLoader('utils/ff_template'))
    template = env.get_template('ffserver.conf')
    stream_map={}
    feeds=[]
    for c in channels:
        feed_id=c.get("name", None)
        if feed_id!=None:
            feeds.append(feed_id)
            url=str("%s.mp4" % feed_id)
            stream_map.update({feed_id: [url,-1]})
        
    streams=feeds
    output_from_parsed_template = template.render(feeds=feeds,streams=streams)
    with open("ffserver.conf", "w") as fh:
        fh.write(output_from_parsed_template)

    return stream_map



def load_configuration(filename):
    conf={}
    config = configparser.ConfigParser()
    config.read(filename)
    
    sections = config.sections()		
    
    for section in sections:
        options = config.options(section)
        conf[section]={}
        for option in options:
            try:
                conf[section][option]=config.get(section,option)
            except:
                print("exception on %s!" % option)
                conf[option]=None
    return conf