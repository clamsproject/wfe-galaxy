#! /usr/bin/env python3
import shutil

import yaml
import subprocess
import os
from os.path import join as pjoin
import xml.etree.ElementTree as ET


STORAGE_PATH = 'storage_path'
APPS = 'apps'
CONSUMERS = 'consumers'
GALAXY_LOCAL_PATH = 'clams-galaxy'
DOCKER_NETWORK_NAME = 'clams-appliance'
CONTAINER_DATA_PATH = '/var/archive'


def get_docker_image_name(app_name):
    return f"clams-{app_name}"


def read_config(config_file_path):
    return yaml.load(open(config_file_path).read())


def download_galaxy_mods():
    if not os.path.exists(GALAXY_LOCAL_PATH):
        git_clone('https://github.com/clamsproject/clams-galaxy.git', GALAXY_LOCAL_PATH, ['--branch', 'dev'])


def create_docker_compose(config, rebuild=False):
    app_names = config[APPS].keys()
    prefixed_app_names = list(map(lambda x: 'app-' + x, app_names))
    consumer_names = config[CONSUMERS].keys()
    if rebuild:
        for name in prefixed_app_names + list(map(lambda x: 'consumer-'+x, consumer_names)) + [GALAXY_LOCAL_PATH]:
            shutil.rmtree(name)
    docker_compose = prep_galaxy(prefixed_app_names, config[STORAGE_PATH])
    process_all_apps(config[APPS], docker_compose)
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
    galaxy_service = get_service_def(GALAXY_LOCAL_PATH, 8080)
    galaxy_service[GALAXY_LOCAL_PATH].update({'privileged': 'true', 'depends_on': dependencies})
    compose_obj['services'].update(galaxy_service)
    add_data_volume(GALAXY_LOCAL_PATH, compose_obj, host_data_path)
    return compose_obj


def get_service_def(dir_name, port):
    return {dir_name: {'image': get_docker_image_name(dir_name), 'container_name': dir_name, 'networks': [DOCKER_NETWORK_NAME], 'ports': [f'{port}:5000']}}


def process_all_apps(apps_config, docker_compose_obj):
    tool_conf_path = pjoin(GALAXY_LOCAL_PATH, 'config', 'tool_conf.xml')
    tool_conf_tree = ET.parse(tool_conf_path)
    for port, (app_name, app_config) in enumerate(apps_config.items(), 8001):
        app_name = f'app-{app_name}'
        download(app_name, app_config)
        build_docker_image(app_name)
        add_to_docker_compose(app_name, docker_compose_obj, port)
        config_xml_tree = gen_app_config_xml(app_name, port)
        add_to_tool_conf_xml(tool_conf_tree, config_xml_tree, app_name)
    tool_conf_tree.write(tool_conf_path, encoding='utf-8')


def get_tool_config_xml_fullpath(app_name):
    return pjoin(GALAXY_LOCAL_PATH, 'tools', get_tool_config_xml_filename(app_name))


def get_tool_config_xml_filename(app_name):
    return get_docker_image_name(app_name) + '.xml'


def process_all_consumers(consumers_config, docker_compose_obj, host_data_path):
    datatypes_conf_path = pjoin(GALAXY_LOCAL_PATH, 'config', 'datatypes_conf.xml')
    datatypes_conf_tree = ET.parse(datatypes_conf_path)
    for port, (consumer_name, consumer_config) in enumerate(consumers_config.items(), 9001):
        consumer_name = f'consumer-{consumer_name}'
        download(consumer_name, consumer_config)
        build_docker_image(consumer_name)
        add_to_docker_compose(consumer_name, docker_compose_obj, port)
        add_data_volume(consumer_name, docker_compose_obj, host_data_path)
        gen_display_app_xml(consumer_name, port, consumer_config['description'])
        add_to_datatypes_conf_xml(datatypes_conf_tree, consumer_name)
    datatypes_conf_tree.write(datatypes_conf_path, encoding='utf-8')


def get_display_app_xml_fullpath(consumer_name):
    return pjoin(GALAXY_LOCAL_PATH, 'display_applications', get_display_app_xml_filename(consumer_name))


def get_display_app_xml_filename(consumer_name):
    return get_docker_image_name(consumer_name) + '.xml'


def add_to_docker_compose(dir_name, docker_compose_obj, port):
    docker_compose_obj['services'].update(get_service_def(dir_name, port))


def add_data_volume(dir_name, docker_compose_obj, host_data_path):
    # 'ro' for read-only
    docker_compose_obj['services'][dir_name].update({'volumes': [f'{host_data_path}:{CONTAINER_DATA_PATH}:ro']})


def build_docker_image(dir_name):
    docker_build(pjoin(dir_name, 'Dockerfile'), dir_name, get_docker_image_name(dir_name))


def gen_app_config_xml(app_name, port):
    curl_cmd = f"curl -X PUT -H 'Content-Type: application/json' -d @$input {app_name}:{port} > $output"
    config_xml_tree = ET.parse(pjoin(app_name, 'config.xml'))
    command_tag = config_xml_tree.find('command')
    command_tag.text = curl_cmd
    del command_tag.attrib['interpreter']
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
    url_tag.text = f'{consumer_name}:{port}'
    param_tag = ET.SubElement(link_tag, 'parms', {'type': 'data', 'name': 'txt_file', 'url': 'galaxy.txt'})
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
                    if os.path.isfile(pjoin(type_path, f_name)):
                        loc_file.write(f'{f_name}\t{pjoin(CONTAINER_DATA_PATH, f_name)}\n')


def download(app_name, app_config):
    if app_config['enabled'] and not os.path.exists(app_name):
        if 'branch' in app_config:
            more_params = ['--branch', app_config['branch']]
        else:
            more_params = []
        git_clone(app_config['repository'], app_name, more_params)


def git_clone(repo_url, clone_dir, more_params=[]):
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
    import argparse
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Make a CLAMS-Galaxy appliance using docker-compose"
    )
    parser.add_argument(
        '-f', '--force-rebuild',
        action='store_true',
        help='Delete existing CLAMS Apps and Galaxy. Then download all and re-build docker images.'
    )
    args = parser.parse_args()


    create_docker_compose(read_config('config.yaml'), args.force_rebuild)
    # subprocess.run(['docker-compose', 'up'])
