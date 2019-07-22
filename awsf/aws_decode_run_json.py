#!/usr/bin/python
import json
import sys

downloadlist_filename = "download_command_list.txt"
input_yml_filename = "inputs.yml"
env_filename = "env_command_list.txt"
INPUT_DIR = "/data1/input"


def main():
    # read json file
    with open(sys.argv[1], 'r') as json_file:
        Dict = json.load(json_file)
        Dict_input = Dict["Job"]["Input"]
        language = Dict["Job"]["App"]["language"]
    # create a download command list file from the information in json
    create_download_command_list(downloadlist_filename, Dict_input, language)
    # create an input yml file to be used on awsem
    if language == 'wdl':  # wdl
        create_input_for_wdl(input_yml_filename, Dict_input)
    elif language == 'snakemake':  # wdl
        create_input_for_snakemake(input_yml_filename, Dict_input)
    else:  # cwl
        create_input_for_cwl(input_yml_filename, Dict_input)
    # create a file that defines environmental variables
    create_env_def_file(env_filename, Dict, language)


def add_download_cmd(data_bucket, data_file, target, profile_flag, f):
    if data_file:
        cmd = "if [[ -z $(aws s3 ls s3://{0}/{1}/) ]]; then aws s3 cp s3://{0}/{1} {2} {3}; else aws s3 cp --recursive s3://{0}/{1} {2} {3}; fi\n"
        f.write(cmd.format(data_bucket, data_file, target, profile_flag))


# create a download command list file from the information in json
def create_download_command_list(downloadlist_filename, Dict_input, language):
    with open(downloadlist_filename, 'w') as f:
        for category in ["Input_files_data", "Secondary_files_data"]:
            for inkey, v in Dict_input[category].iteritems():
                if inkey.startswith('file://'):
                    if language not in ['shell', 'snakemake']:
                        raise Exception('input file has to be defined with argument name for CWL and WDL')
                    target = inkey.replace('file://', '')
                    if not target.startswith('/data1/'):
                        raise Exception('input target directory must be in /data1/')
                    if not target.startswith('/data1/' + language) and \
                        not target.startswith('/data1/input') and \
                        not target.startswith('/data1/out'):
                            raise Exception('input target directory must be in /data1/input, /data1/out or /data1/%s' % language)
                else:
                    target = ''
                    target_template = INPUT_DIR + "/%s"
                data_bucket = v["dir"]
                profile = v.get("profile", '')
                profile_flag = "--profile " + profile if profile else ''
                path1 = v["path"]
                rename1 = v.get("rename", None)
                if not rename1:
                    rename1 = path1
                if isinstance(path1, list):
                    for path2, rename2 in zip(path1, rename1):
                        if isinstance(path2, list):
                            for path3, rename3 in zip(path2, rename2):
                                if isinstance(path3, list):
                                    for data_file, rename4 in zip(path3, rename3):
                                        target = target_template % rename4
                                        add_download_cmd(data_bucket, data_file, target, profile_flag, f)
                                else:
                                    data_file = path3
                                    target = target_template % rename3
                                    add_download_cmd(data_bucket, data_file, target, profile_flag, f)
                        else:
                            data_file = path2
                            target = target_template % rename2
                            add_download_cmd(data_bucket, data_file, target, profile_flag, f)
                else:
                    data_file = path1
                    if not target:
                        target = target_template % rename1
                    add_download_cmd(data_bucket, data_file, target, profile_flag, f)


def file2cwlfile(filename, dir):
    return {"class": 'File', "path": dir + '/' + filename}


# create an input yml file for cwl-runner
def create_input_for_cwl(input_yml_filename, Dict_input):
    with open(input_yml_filename, 'w') as f_yml:
        inputs = Dict_input.copy()
        yml = {}
        for category in ["Input_parameters"]:
            for item, value in inputs[category].iteritems():
                yml[item] = value
        for category in ["Input_files_data"]:
            for item in inputs[category].keys():
                v = inputs[category][item]
                if 'dir' in v:
                    del v['dir']
                if 'profile' in v:
                    del v['profile']
                if 'rename' in v and v['rename']:
                    if isinstance(v['rename'], list):
                        v['path'] = v['rename'].copy()
                    else:
                        v['path'] = v['rename']
                    del v['rename']
                if isinstance(v['path'], list):
                    v2 = []
                    for pi in v['path']:
                        if isinstance(pi, list):
                            nested = []
                            for ppi in pi:
                                if isinstance(ppi, list):
                                    nested.append([file2cwlfile(pppi, INPUT_DIR) for pppi in ppi])
                                else:
                                    nested.append(file2cwlfile(ppi, INPUT_DIR))
                            v2.append(nested)
                        else:
                            v2.append(file2cwlfile(pi, INPUT_DIR))
                    v = v2
                    yml[item] = v
                else:
                    v['path'] = INPUT_DIR + '/' + v['path']
                    yml[item] = v.copy()
        json.dump(yml, f_yml, indent=4, sort_keys=True)


def create_input_for_wdl(input_yml_filename, Dict_input):
    with open(input_yml_filename, 'w') as f_yml:
        inputs = Dict_input.copy()
        yml = {}
        for category in ["Input_parameters"]:
            for item, value in inputs[category].iteritems():
                yml[item] = value
        for category in ["Input_files_data"]:
            for item in inputs[category].keys():
                v = inputs[category][item]
                if 'rename' in v and v['rename']:
                    if isinstance(v['rename'], list):
                        v['path'] = list(v['rename'])
                    else:
                        v['path'] = v['rename']
                    del v['rename']
                if isinstance(v['path'], list):
                    yml[item] = []
                    for pi in v['path']:
                        if isinstance(pi, list):
                            nested = []
                            for ppi in pi:
                                if isinstance(ppi, list):
                                    nested.append([INPUT_DIR + '/' + pppi for pppi in ppi])
                                else:
                                    nested.append(INPUT_DIR + '/' + ppi)
                            yml[item].append(nested)
                        else:
                            yml[item].append(INPUT_DIR + '/' + pi)
                else:
                    yml[item] = INPUT_DIR + '/' + v['path']
        json.dump(yml, f_yml, indent=4, sort_keys=True)


def create_input_for_snakemake(input_yml_filename, Dict_input):
    pass  # for now assume no input yml


# create a file that defines environmental variables
def create_env_def_file(env_filename, Dict, language):
    # I have to use these variables after this script finishes running.
    # I didn't use os.environ + os.system('bash') because that would remove the other
    # env variables set before this script started running.
    with open(env_filename, 'w') as f_env:
        if language == 'wdl':
            f_env.write("export WDL_URL={}\n".format(Dict["Job"]["App"]["wdl_url"]))
            f_env.write("export MAIN_WDL={}\n".format(Dict["Job"]["App"]["main_wdl"]))
            f_env.write("export WDL_FILES=\"{}\"\n".format(' '.join(Dict["Job"]["App"]["other_wdl_files"].split(','))))
        elif language == 'snakemake':
            f_env.write("export SNAKEMAKE_URL={}\n".format(Dict["Job"]["App"]["snakemake_url"]))
            f_env.write("export MAIN_SNAKEMAKE={}\n".format(Dict["Job"]["App"]["main_snakemake"]))
            f_env.write("export SNAKEMAKE_FILES=\"{}\"\n".format(' '.join(Dict["Job"]["App"]["other_snakemake_files"].split(','))))
            f_env.write("export COMMAND=\"{}\"\n".format(Dict["Job"]["App"]["command"].replace("\"", "\\\"")))
            f_env.write("export CONTAINER_IMAGE={}\n".format(Dict["Job"]["App"]["container_image"]))
        elif language == 'shell':
            f_env.write("export COMMAND=\"{}\"\n".format(Dict["Job"]["App"]["command"].replace("\"", "\\\"")))
            f_env.write("export CONTAINER_IMAGE={}\n".format(Dict["Job"]["App"]["container_image"]))
        else:  # cwl
            f_env.write("export CWL_URL={}\n".format(Dict["Job"]["App"]["cwl_url"]))
            f_env.write("export MAIN_CWL={}\n".format(Dict["Job"]["App"]["main_cwl"]))
            f_env.write("export CWL_FILES=\"{}\"\n".format(' '.join(Dict["Job"]["App"]["other_cwl_files"].split(','))))
        # other env variables
        f_env.write("export OUTBUCKET={}\n".format(Dict["Job"]["Output"]["output_bucket_directory"]))
        f_env.write("export PUBLIC_POSTRUN_JSON={}\n".format('1' if Dict["config"].get('public_postrun_json', False) else '0'))
        env_preserv_str = ''
        if "Env" in Dict["Job"]["Input"]:
            for ev, val in Dict["Job"]["Input"]["Env"].iteritems():
                f_env.write("{}={}\n".format(ev, val))
                env_preserv_str = env_preserv_str + "--preserve-environment " + ev + " "
        f_env.write("export PRESERVED_ENV_OPTION=\"{}\"\n".format(env_preserv_str))


main()
