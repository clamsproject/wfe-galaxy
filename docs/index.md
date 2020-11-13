---
layout: page
title: CLAMS appliance
subtitle: 
---

The CLAMS appliance provides a *turn-key* installation of CLAMS-Galaxy instance. Configure your CLAMS instance in a simple YAML file and run it via Docker. 

##### NOTE: Currently the appliance is under active development and not all pieces are guaranteed to work. Always check with this documentation, and leave us comments or issue reports using [the issue tracker](https://github.com/clamsproject/appliance/issues), when you have problems. 

----
## Requirements 

* [`docker`](https://www.docker.com/)
* [`docker-compose`](https://docs.docker.com/compose/)
* [`python`](https://www.python.org/) (3.6 or later)
  * [`PyYAML`](https://pypi.org/project/PyYAML/) (`pip install pyyaml`)
* [`git`](https://git-scm.com/)

#### Recommendations

* `docker` (and `docker-compose`) runs natively on GNU/Linux, and thus runs faster in many scenarios. 
* Some CLAMS apps require large RAM to run or large HDD space to build. We recommend 8GB RAM and ~100GB storage at minimum. If you're on Mac or Windows, it's recommended to increase RAM and HDD of the docker VM. (see [this](https://docs.docker.com/docker-for-mac/space/))

----
## tl;dr

Clone the appliance from the github repository and change the configuration in the `config.yaml` file. Run `make-appliance.py` to build docker images and docker-compose configuration. Finally start a docker network using the docker-compose. 

----
## Download

Use `git` to download code from this repository. 
```bash 
git clone https://github.com/clamsproject/appliance.git
```

----
## Configuration

### Understanding components in the appliance
Before running a CLAMS appliance, one must configure the appliance with desired CLAMS apps, MMIF consumers, as well as the storage path of the archival material to process. 
All configuration are provided via `config.yaml` file. 
While making an appliance (using `make-appliance.py` script), the maker will download all configured apps and consumers and build docker images for each of them. 
Those dockerized apps (and consumers) will be automatically integrated into a customized [Galaxy workflow engine](https://galaxyproject.org/), which will serve as the primary graphical user interface (GUI) for archivists. 
Additionally, the maker will also find all flies under the archive path and create a media selector tool for the Galaxy instance. 

#### Where can I find CLAMS apps? 
Team CLAMS is working hard to publish various computational analysis tools as CLAMS apps. 
You can find all apps we have developed or wrapped at our github organization at https://github.com/clamsproject. Search for `app-` and the repositories start with `app-` prefix are individual apps. 
However, not all CLAMS apps are compatible with the appliance. We are working on developing a public registry of open CLAMS apps, and by doing so, our goal is to require all of them to be appliance-compatible. In the meantime, if you find a `Dockerfile` (not `dockerfile`) under a repository, the app is likely to work in appliance. 

If you have computational analysis tools that you want to run on CLAMS appliance, you can also write your own wrapper using the CLAMS Python SDK. For more information on the SDK and tutorials for writing CLAMS apps, please refer to [the `clams-python` documentation](https://clams.ai/clams-python). 

#### What is a MMIF consumer? 
Multi-Media Interchange Format, or [**MMIF**](https://mmif.clams.ai/) is a JSON(-LD)-based data format we use in the CLAMS platform. MMIF supports transparent interoperability between computational analysis tools and software, so that users of the tools can create and customize different pipelines to extract meaningful information and insights from digitized audiovisual material.
However because of transparency that MMIF provides, often MMIF files carries lots of metadata about the pipelines and tools themselves that are not always so meaningful to the end users (e.g. archivist)
MMIF consumers, in the context of the CLAMS appliance, are software that process final MMIF outputs and create more meaningful data out of MMIF for specific purposes. We provide with the appliance a couple example consumers that render the MMIF json data into HTML pages to visualize the analysis results for human readers. Other use cases would be, for example, trimming and filtering information buried in MMIF data, converting MMIF data into something else (e.g. CSV, [IIIF](https://iiif.io/), [PBCore](https://pbcore.org/)), or sending the data to a persistent storage. Consumers must be written as a HTTP web application, implementing specific HTTP APIs. For more information on writing your own consumers, please also refer to [the `clams-python` documentation](https://clams.ai/clams-python). 

#### How to provide the appliance with media files? 

The appliance will be running as a network of docker containers, sharing a common *archive* folder located in the host machine. In the future, we will support direct network mounts, but currently only locally mounted folders are supported. It doesn't matter where the archive folder is mounted on the host machine. But for security reasons, we highly recommend NOT to place it in a system directory (such as the root `/`). In that *archive* folder, users must create four sub-directories; `video`, `audio`, `image`, and `text`. And actual media files should be placed (either physically or symbolically) under one of those sub-directory based on the type of the media. 

### YAML config
An example configuration file is provided as [config.yaml](config.yaml). Configuration file must be written in [YAML](https://yaml.org/start.html) format and has three top-level sections; `storage_path`, `apps`, and `consumers`. 

* `storage_path` (storage configuration): Local directory name where data (video, audio, image, and/or text) is stored. Data must be organized under subdirectories `video`, `audio`, `image`, and `test` based on the file type. The appliance does not check actual MIME types or file extensions of those files while building CLAMS-Galaxy instance. So it is users' responsibility to make sure each subdirectory contains proper files. 
* `apps` (CLAMS apps configuration): List of CLAMS app objects. An app object is essentially a pointer to an accessible git repository that holds source code (including a `Dockerfile` and optionally `config.xml` for Galaxy) of the app. An object has to have a human friendly alias as the key of the object that associated with `repository`, `branch`, `description`, `type` and `enabled` key-value pairs. For example; 
  ``` yaml
  puakaldi:
    enabled: True
    repository: https://github.com/clamsproject/app-puakaldi-wrapper.git
    branch: develop
    description: "PopUp Archive Kaldi ASR"
    type: Audio,Alignment
  ```
  * key: single-token name of the app. This will be used to name local docker images names and Galaxy tool ID. 
  * `repository`: a git address to obtain the app source code (must be publicly accessible).
  * `enabled`: `True` to include in the appliance, `False` to exclude. 
  * `description`: a short human friendly description of the app. This value will be shown as the tool name in the Galaxy UI. 
  * `type`: a comma-separated list of app types. Values can be `Video`, `Audio`, `Text`, `Image`, and `Alignment`. (case insensitive)
  * `branch` (optional): if the code to use is not on the default github branch (typically `master` or `main`), use this optional key to specify git branch or tag name of the code to use. This value will be shown as the app version in the Galaxy GUI. 
* `consumers` (MMIF consumers configuration): List of MMIF consumer app objects. MMIF is output file from CLAMS app (json formatted). Using `consumers` configuration, you can add buttons to call external software that use MMIF as input (e.g. for visualization) to the Galaxy interface. All key in a consumer object have mostly identical meanings to those of an app object, except for the `type` has no meaning in consumer configuration. 
  ``` yaml
  mmif-viz:
    enabled: True
    repository: https://github.com/clamsproject/mmif-visualizer.git
    description: "Display MMIF annotations"
  ```

----
## Build 

First install python dependencies specified in the [`requirements.txt`](requirements.txt). 

```
pip install -r requirements.txt
```

Then run `make-appliance.py`. Optionally you can pass `-f` flag to ignore any cached docker images and build everything from scratch. 
```
python make-appliance.py
```

----
## Deployment

Once all apps and consumers are built (may take hours depending on the number of apps and their dependencies), `docker-compose.yml` file will be generated. You can now start a CLAMS-Galaxy instance with `docker-compose`, in the same directory where the `docker-compose.yml` file was generated. 
```
docker-compose up
```

When the CLAMS-Galaxy instance spins up, CLAMS app containers will use host machine's ports starting from 8001 (each uses a port), and MMIF consumers will use ports from 9001. The Galaxy will be listening to host's port 8080. So make sure those ports are available before starting up the CLAMS instance. Once everything is up and running, you can connect to the CLAMS-Galaxy via http://localhost:8080 or other host addresses. 

### Galaxy Administration 

A new admin account for Galaxy web interface will be created at the first run. Once Galaxy is up and running, you can log in using `admin` for user name and `password` for the password (YES, super-secure credential!). The appliance is still experimental and supposed to be running on a local machine. We will continue developing the appliance for more secure and scalable deployment of the CLAMS. 


### Shutdown 

To shutdown a running CLAMS appliance instance, just press `ctrl`-`c` to stop the containers. Or you can issue `docker-compose down` under the same directory in a separate terminal to stop *and* remove containers. 
All Galaxy-internal databases (users, admins, job history, and intermediate output files) are written to a automatically generated docker volume, and the volume will be removed when the Galaxy container is removed. 
So when you want to re-use those files (e.g. intermediate MMIF outputs), just use `ctrl`-`c` and later you can restart the network by `docker-compose up`. 

