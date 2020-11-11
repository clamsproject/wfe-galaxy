#! /usr/bin/env python3
import yaml

import socket
import subprocess
import os
from os.path import join as pjoin
import xml.etree.ElementTree as ET


STORAGE_PATH = 'storage_path'
APPS = 'apps'
APP_PREFIX = 'app-'
CONSUMERS = 'consumers'
CONSUMER_PREFIX = 'consumer-'
# local directory to clone clams-galaxy on the host
GALAXY_LOCAL_PATH = 'clams-galaxy'
# hostname given to the container instantiated from the cloned clams-galaxy
GALAXY_CONTNAME = 'clams-galaxy'
# fixed by galaxy-stable image
GALAXY_CONTPORT = '80'
GALAXY_HOSTPORT = '8080'
DOCKER_NETWORK_NAME = 'clams-appliance'
CONTAINER_DATA_PATH = '/var/archive'
HOSTNAME = socket.gethostname()
DEVELOP=False


def get_docker_image_name(app_name):
    return f"clams-{app_name}"


def clean(directory):
    import shutil
    for f in os.listdir(directory):
        if f.startswith(APP_PREFIX) or f.startswith(CONSUMER_PREFIX) or f == GALAXY_LOCAL_PATH:
            d = pjoin('.', f)
            if os.path.islink(d):
                os.unlink(d)
            elif os.path.isdir(d):
                shutil.rmtree(d)
    try:
        os.remove('docker-compose.yml', )
    except OSError:
        pass


def read_config(config_file_path):
    configs = yaml.load(open(config_file_path).read())
    configs[STORAGE_PATH] = os.path.expandvars(os.path.expanduser(configs[STORAGE_PATH]))
    return configs


def download_galaxy_mods():
    if not os.path.exists(GALAXY_LOCAL_PATH):
        git_clone('https://github.com/clamsproject/clams-galaxy.git', GALAXY_LOCAL_PATH, [])


def create_docker_compose(config, rebuild=False, develop=False):
    global DEVELOP
    DEVELOP = develop
    if rebuild:
        clean('.')
    prefixed_app_names = list(map(lambda x: APP_PREFIX + x, config[APPS].keys()))
    docker_compose = prep_galaxy(prefixed_app_names, config[STORAGE_PATH])
    process_all_apps(config[APPS], docker_compose, config[STORAGE_PATH])
    process_all_consumers(config[CONSUMERS], docker_compose, config[STORAGE_PATH])
    gen_db_loc_files(config[STORAGE_PATH])
    docker_build(pjoin(GALAXY_LOCAL_PATH, 'Dockerfile'), GALAXY_LOCAL_PATH, get_docker_image_name(GALAXY_LOCAL_PATH), use_cached=False)
    with open('docker-compose.yml', 'w') as compose_file:
        yaml.SafeDumper.add_representer(
            type(None),
            lambda dumper, value: dumper.represent_scalar(u'tag:yaml.org,2002:null', '')
        )
        print(yaml.safe_dump(docker_compose))
        compose_file.write((yaml.dump(docker_compose)))


def create_base_compose_obj():
    return {'version': '3', 'services': {}, 'networks': {DOCKER_NETWORK_NAME: None}}


def prep_galaxy(dependencies, host_data_path):
    download_galaxy_mods()
    compose_obj = create_base_compose_obj()
    galaxy_service = get_service_def(GALAXY_CONTNAME, int(GALAXY_HOSTPORT))
    # even though we configure `http` address to be bound to 0.0.0.0:5000 in galaxy.yml, 
    # external communication still needs to be using port 80 for underlying wsgi modules to work
    galaxy_service[GALAXY_CONTNAME].update({'privileged': 'true', 'depends_on': dependencies, 'ports': [f'{GALAXY_HOSTPORT}:{GALAXY_CONTPORT}']})
    compose_obj['services'].update(galaxy_service)
    add_data_volume(GALAXY_CONTNAME, compose_obj, host_data_path)
    return compose_obj


def get_service_def(cont_hostname, port):
    service_def = {cont_hostname: {
        'image': get_docker_image_name(cont_hostname),
        'container_name': cont_hostname,
        'networks': [DOCKER_NETWORK_NAME],
    }}
    if port != 5000:
        service_def[cont_hostname]['ports'] = [f'{port}:5000']
    return service_def


def process_all_apps(apps_config, docker_compose_obj, host_data_path):
    tool_conf_path = pjoin(GALAXY_LOCAL_PATH, 'config', 'tool_conf.xml')
    tool_conf_tree = ET.parse(tool_conf_path)
    port = 5000
    for host_port, (app_name, app_config) in enumerate(apps_config.items(), 8001):
        app_name = f'{APP_PREFIX}{app_name}'
        download(app_name, app_config)
        build_docker_image(app_name)
        add_to_docker_compose(app_name, docker_compose_obj, port)
        add_data_volume(app_name, docker_compose_obj, host_data_path)
        config_xml_tree = gen_app_config_xml(app_name, app_config, port)
        add_to_tool_conf_xml(tool_conf_tree, config_xml_tree, app_name)
    tool_conf_tree.write(tool_conf_path, encoding='utf-8', xml_declaration=True)


def get_tool_config_xml_fullpath(app_name):
    return pjoin(GALAXY_LOCAL_PATH, 'tools', get_tool_config_xml_filename(app_name))


def get_tool_config_xml_filename(app_name):
    return get_docker_image_name(app_name) + '.xml'


def process_all_consumers(consumers_config, docker_compose_obj, host_data_path):
    datatypes_conf_path = pjoin(GALAXY_LOCAL_PATH, 'config', 'datatypes_conf.xml')
    datatypes_conf_tree = ET.parse(datatypes_conf_path)
    for port, (consumer_name, consumer_config) in enumerate(consumers_config.items(), 9001):
        consumer_name = f'{CONSUMER_PREFIX}{consumer_name}'
        download(consumer_name, consumer_config)
        build_docker_image(consumer_name)
        add_to_docker_compose(consumer_name, docker_compose_obj, port)
        add_data_volume(consumer_name, docker_compose_obj, host_data_path, flask_static=True)
        gen_display_app_xml(consumer_name, port, consumer_config['description'])
        add_to_datatypes_conf_xml(datatypes_conf_tree, consumer_name)
    datatypes_conf_tree.write(datatypes_conf_path, encoding='utf-8')


def get_display_app_xml_fullpath(consumer_name):
    return pjoin(GALAXY_LOCAL_PATH, 'display_applications', get_display_app_xml_filename(consumer_name))


def get_display_app_xml_filename(consumer_name):
    return get_docker_image_name(consumer_name) + '.xml'


def add_to_docker_compose(cont_hostname, docker_compose_obj, port):
    docker_compose_obj['services'].update(get_service_def(cont_hostname, port))


def add_data_volume(cont_hostname, docker_compose_obj, host_data_path, flask_static=False):
    # 'ro' for read-only
    docker_compose_obj['services'][cont_hostname].update({'volumes': [f'{host_data_path}:{CONTAINER_DATA_PATH}:ro']})
    if flask_static: 
        docker_compose_obj['services'][cont_hostname]['volumes'].append(f'{host_data_path}:/app/static/{CONTAINER_DATA_PATH}:ro')


def build_docker_image(dir_name):
    docker_build(pjoin(dir_name, 'Dockerfile'), dir_name, get_docker_image_name(dir_name))


def gen_app_config_xml(app_name, app_config, port):
    curl_cmd = f"curl -s -X PUT -H 'Content-Type: application/json' -d @$input {app_name}:{port} > $output"
    if os.path.exists(pjoin(app_name, 'config.xml')):
        config_xml_tree = ET.parse(pjoin(app_name, 'config.xml'))
        command_tag = config_xml_tree.find('command')
        command_tag.text = curl_cmd
        del command_tag.attrib['interpreter']
    else:
        # create from scratch
        tool_tag = ET.Element('tool')
        tool_tag.set('id', app_name)
        tool_tag.set('name', app_config['description'])
        tool_tag.set('version', app_config['branch'] if 'branch' in app_config else 'upstream')
        tool_tag.append(ET.Comment('Generated by CLAMS appliance maker'))

        description_tag = ET.SubElement(tool_tag, 'description')
        description_tag.text = f'{app_config["description"]} (This tool is automatically configured by CLAMS appliance maker)'
        command_tag = ET.SubElement(tool_tag, 'command')
        command_tag.text = curl_cmd

        inputs_tag = ET.SubElement(tool_tag, 'inputs')
        input_param_tag = ET.SubElement(inputs_tag, 'param')
        input_param_tag.set('name', 'input')
        input_param_tag.set('type', 'data')
        input_param_tag.set('format', 'json')
        input_param_tag.set('label', 'Input MMIF')

        outputs_tag = ET.SubElement(tool_tag, 'outputs')
        output_data_tag = ET.SubElement(outputs_tag, 'data')
        output_data_tag.set('name', 'output')
        output_data_tag.set('format', 'json')
        output_data_tag.set('label', f'{app_name} annotations')

        help_tag = ET.SubElement(tool_tag, 'help')
        help_tag.text = app_config['type'].title()

        config_xml_tree = ET.ElementTree(tool_tag)

    config_xml_tree.write(pjoin(get_tool_config_xml_fullpath(app_name)), encoding='utf-8')
    return config_xml_tree


def add_to_tool_conf_xml(tool_conf_tree: ET.ElementTree, config_xml_tree: ET.ElementTree, app_name):
    categories = config_xml_tree.find('help').text.split(',')
    tool_tag = ET.Element('tool', {'file': get_tool_config_xml_filename(app_name)})
    for category in categories:
        category_exists = False
        for section in tool_conf_tree.findall('section'):
            if section.attrib['id'] == category:
                section.append(tool_tag)
                category_exists = True
        if not category_exists:
            section_tag = ET.Element('section', {'id': category, 'name': f"{category} Apps"})
            section_tag.append(tool_tag)
            tool_conf_tree.getroot().append(section_tag)


def gen_display_app_xml(consumer_name, port, description):
    display_tag = ET.Element('display', {'id': consumer_name, 'version': '1.0.0', 'name': description})
    link_tag = ET.SubElement(display_tag, 'link', {'id': 'open', 'name': 'open'})
    url_tag = ET.SubElement(link_tag, 'url')
    url_tag.text = f'http://{HOSTNAME}:{port}/display?file=${{qp("/".join($txt_file.url.split("/")[:2] + ["{GALAXY_CONTNAME}:{GALAXY_CONTPORT}"] + $txt_file.url.split("/")[3:]))}}'
    param_tag = ET.SubElement(link_tag, 'param', {'type': 'data', 'name': 'txt_file', 'url': 'galaxy.txt'})
    ET.ElementTree(display_tag).write(pjoin(get_display_app_xml_fullpath(consumer_name)), encoding='utf-8')


def add_to_datatypes_conf_xml(datatypes_conf_tree: ET.ElementTree, consumer_name):
    display_tag = ET.Element('display', {'file': get_display_app_xml_filename(consumer_name)})
    for dt in datatypes_conf_tree.find('registration').findall('datatype'):
        if dt.attrib['extension'] == 'json':
            dt.append(display_tag)


def gen_db_loc_files(host_data_path):
    for mtype in ['text', 'video', 'image', 'audio']:
        type_path = pjoin(host_data_path, mtype)
        if os.path.exists(type_path) and os.path.isdir(type_path):
            with open(pjoin(GALAXY_LOCAL_PATH, 'tool-data', f'{mtype}db.loc'), 'w') as loc_file:
                for f_name in os.listdir(type_path):
                    if os.path.isfile(pjoin(type_path, f_name)) and not f_name.startswith('.'):
                        loc_file.write(f'{f_name}\t{pjoin(CONTAINER_DATA_PATH, mtype, f_name)}\n')


def download(app_name, app_config):
    if app_config['enabled'] and not os.path.exists(app_name):
        if 'branch' in app_config:
            more_params = ['--branch', app_config['branch']]
        else:
            more_params = []
        git_clone(app_config['repository'], app_name, more_params)


def git_clone(repo_url, clone_dir, more_params=[]):
    if DEVELOP:
        os.symlink(pjoin('..', clone_dir), clone_dir)
    else:
        subprocess.run(['git', 'clone', '--depth', '1'] + more_params + [ repo_url, clone_dir])


def docker_build(docker_file_path, build_context, image_name, use_cached=True):
    build_cmd = ['docker', 'build', '-t', image_name, '-f', docker_file_path, build_context]
    if not use_cached:
        build_cmd += ['--no-cache']
    subprocess.run(build_cmd)


def docker_run(image_name, container_name):
    subprocess.run(['docker', 'run', '--rm', '--name', container_name, '-d', image_name])


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description="Make a CLAMS-Galaxy appliance using docker-compose"
    )
    parser.add_argument(
        '-d', '--develop',
        action='store_true',
        help='Run the script in *develop* mode. In develop mode Galaxy, apps, and consumers are copied from local file system, instead of being downloaded from github.'
    )
    parser.add_argument(
        '-f', '--force-rebuild',
        action='store_true',
        help='Delete existing CLAMS Apps and Galaxy. Then download all and re-build docker images.'
    )
    args = parser.parse_args()

    create_docker_compose(read_config('config.yaml'), args.force_rebuild, args.develop)
    # subprocess.run(['docker-compose', 'up'])
