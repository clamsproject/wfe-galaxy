# CLAMS appliance 

The CLAMS appliance provides a *turn-key* installation of CLAMS-Galaxy instance. Currently it is under development not all pieces are guaranteed to work. All software in this code repository is provided only on an as-is basis. See [our license](LICENSE) for more details. 

## Requirements 

* [*docker*](https://www.docker.com/)
* [*docker-compose*](https://docs.docker.com/compose/)
* [*python*](https://www.python.org/) 3.6 or later
* [*git*](https://git-scm.com/)

## Download

Use `git clone` to download code from this repository. 

## Configuration

An example configuration file is provided as [config.yaml](config.yaml). Configuration file must be written in [YAML](https://yaml.org/start.html) format and has three parts; storage, apps, and consumers. 

* `storage_path` (storage configuration): Local directory name where data (video, audio, and/or text) is stored. Note that in the final Galaxy interface, there will be data 'getters' (e.g. file uploader) come with the Galaxy by default. However CLAMS-Galaxy does NOT support those getters, hence all data for processing should be passed using this directory. Also data must be organized under subdirectories `video`, `audio`, `text`, and `image` based on the file type. The appliance does not check actual MIME types or file extensions of those files while building CLAMS-Galaxy instance. So it is users' responsibility to make sure each subdirectory contains proper files. 
* `apps` (CLAMS app configuration): List of CLAMS app objects. An app object is essentially a pointer to an open git repository that holds source code (including galaxy config and a dockerfile) of the app. An object has to have a human friendly alias as the key of the object that associated with `repository`, `branch`, and `enabled` key-value pairs. For example; 
  ``` yaml
  gentle-pretokens:
    enabled: True
    repository: https://github.com/clamsproject/app-gentle-forced-aligner.git
    branch: pretokens
  ```
  * `repository`: a git address to obtain the app source code.
  * `enabled`: `True` to include in the appliance, `False` to exclude. 
  * `branch` (optional): if the code to use is not on the `master` branch, use this optional key to specify git branch or tag name of the code to use. 
* `consumers` (MMIF consumer configuration): List of MMIF consumer app objects. MMIF is output file from CLAMS app (json formatted). Using `consumers` configuration, you can add buttons to call external software that use MMIF as input (e.g. for visualization) to the Galaxy interface. Addition to three configuration keys for an app object (`enabled`, `repository`, `branch`), a consumer object must be configured with `description` field that holds a short human friendly description of the external software. For example; 
  ``` yaml
  mmif-viz:
    enabled: True
    repository: https://github.com/clamsproject/mmif-visualizer.git
    description: "Display MMIF annotations"
  ```

## Build 

First install python dependencies specified in the [`requirements.txt`](requirements.txt). 

```
pip install -r requirements.txt
```

Then run `make-appliance.py`. Optionally you can pass `-f` flag to ignore any cached docker images and build everything from scratch. 
```
python make-appliance.py
```

Once all apps and consumers are built (may take hours depending on the number of apps and their dependencies), `docker-compose.yml` file will be generated. You can now start a CLAMS-Galaxy instance with `docker-compose`. 
```
docker-compose . -f ./docker-compose.yml
```

When the CLAMS-Galaxy instance spins up, CLAMS app containers will use host machine's ports starting from 8001 (each uses a port), and MMIF consumers will use ports from 9001. The Galaxy will be listening to host's port 8080. So make sure those ports are available before starting up the CLAMS instance. Once everything is up and running, you can connect to the CLAMS-Galaxy via http://localhost:8080 .

