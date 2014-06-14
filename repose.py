#!/usr/bin/python

__author__ = "Dimitry Ushakov"

# This is a DOCUMENTATION stub specific to this module, it extends
# a documentation fragment located in ansible.utils.module_docs_fragments
DOCUMENTATION = '''
---
module: repose
short_description: create (starts) / delete (stop) an instance of Repose
description:
     - creates / deletes a Repose instance and optionally
       waits for it to be 'running'.
options:
  release:
    description:
      - Specifies which release version to deploy and start
    default: null
  git_build:
    description:
      - Whether or not to build repose from source (git)
    default: no
  git_repo:
    description:
      - Which git repository to pull repose from
    default: https://github.com/rackerlabs/repose
  git_branch:
    description:
      - Which git branch to pull repose from
    default: master
  state:
    description:
      - Indicate desired state of repose
    choices:
      - present
      - absent
    default: present
  wait:
    description:
      - wait for the instance to be in state 'running' before returning
    default: "yes"
    choices:
      - "yes"
      - "no"
  wait_timeout:
    description:
      - how long before wait gives up, in seconds
    default: 300
author: Dimitry Ushakov
'''

EXAMPLES = '''
- name: Build a Repose instance with latest version and wait until started
  gather_facts: False
  tasks:
    - name: Build Repose Instance
      local_action:
        module: repose
      register: repose_module

- name: Build a Repose instance with specific version and do not wait
  hosts: local
  gather_facts: False
  tasks:
    - name: Build Repose Instance
      local_action:
        module: repose
        state: present
        release: 5.0
        wait: no
      register: repose_module

- name: Build a Repose instance from a specific git repo
  hosts: local
  gather_facts: False
  tasks:
    - name: Build Repose Instance
      local_action:
        module: repose
        state: present
        git_build: yes
        git_repo: https://github.com/rackerlabs/repose
        git_branch: dimtruck
        wait: no
      register: repose_module

- name: Shut down a Repose instance
  hosts: local
  gather_facts: False
  tasks:
    - name: Build Repose Instance
      local_action:
        module: repose
        state: absent
      register: repose_module
'''

import shutil
import glob
import os
import commands


def check_if_repose_started():
    output = commands.getoutput('ps aux | grep repose-valve').split('\n')
    return output >= 3


def started_repose_id():
    output = commands.getoutput('ps aux | grep repose-valve').split('\n')
    for i in output:
        if not 'grep repose-valve' in i:
            return i.split()[1]
    return None


def stop_repose_id(module, pid):
    # stop repose id here
    module.run_command('kill -9 %s' % pid)


def build_with_git(module, git_repo, git_branch, wait, wait_timeout):

    # 1. get from github (git_repo/git_branch) (git is a dependency)
    # 2. build with maven (mvn is a dependency)
    # 3. take 2 EARs and deploy to /usr/share/repose/filters
    # 4. take JAR and deploy to /usr/share/lib/repose
    # 5. take configurations and parse into /etc/repose
    # 6. start repose
    changed = False
    if check_if_repose_started():
        untouched = dict(
            pid=started_repose_id(),
            status='STARTED'
        )
    module.run_command('mkdir -p /opt/repose')
    module.run_command('git init', use_unsafe_shell=True,
                       check_rc=True, cwd='/opt/repose')
    module.run_command('git pull %s %s' % (git_repo, git_branch),
                       use_unsafe_shell=True, check_rc=True, cwd='/opt/repose')
    module.run_command('mkdir -p /usr/share/repose/filters')
    module.run_command('mkdir -p /usr/share/lib/repose')
    module.run_command('mkdir -p /etc/repose')
    (repose_valve, extensions_bundle, filter_bundle) = (
        '/usr/share/lib/repose/repose-valve.jar',
        '/usr/share/repose/filters/extensions-filter-bundle.ear',
        '/usr/share/repose/filters/filter-bundle.ear')
    shutil.copy(
        '/opt/repose/repose-aggregator/core/valve/target/repose-valve.jar',
        repose_valve)
    for ext_file in glob.glob(r'/opt/repose/repose-aggregator/extensions/'
                          r'extensions-filter-bundle/target/'
                          r'extensions-filter-bundle-*-SNAPSHOT.ear'):
        print ext_file
        shutil.copy(ext_file, extensions_bundle)
    for filter_file in glob.glob(r'/opt/repose/repose-aggregator/components/'
                                r'filters/filter-bundle/target/'
                                r'filter-bundle-*-SNAPSHOT.ear'):
        print filter_file
        shutil.copy(filter_file, filter_bundle)
    module.run_command('nohup java -jar repose-valve.jar -s 8123 -c '
                       '/etc/repose start', use_unsafe_shell=True,
                       check_rc=True, cwd='/usr/share/lib/repose')

    if wait:
        end_time = time.time() + wait_timeout
        infinite = wait_timeout == 0
        while infinite or time.time() < end_time:
            if check_if_repose_started():
                changed = True
                break
            else:
                time.sleep(5)
    validate_repose(module, changed, untouched)


def build_with_release(module, release, package, wait, wait_timeout):

    # 1. check which os it is (DEB or RPM)
    # 2. install repose
    # 3. call repose-valve to start repose
    changed = False
    if check_if_repose_started():
        untouched = dict(
            pid=started_repose_id(),
            status='STARTED'
        )
    else:
        if package in ('Ubuntu', 'Debian'):
            module.run_command('apt-get update && apt-get install '
                               'repose-valve %s -y -q' % release,
                               use_unsafe_shell=True, check_rc=True)
            # start repose from repose-valve
            module.run_command('service repose-valve start')
        elif package == ('RedHat', 'Fedora', 'CentOS'):
            module.run_command('yum update && yum install repose-valve %s'
                               ' -y -q' % release,
                               use_unsafe_shell=True, check_rc=True)
            # start repose from repose-valve
            module.run_command('service repose-valve start')
        else:
            module.fail_json(msg='Invalid package specified: %s' & package)

        if wait:
            end_time = time.time() + wait_timeout
            infinite = wait_timeout == 0
            while infinite or time.time() < end_time:
                if check_if_repose_started():
                    changed = True
                    break
                else:
                    time.sleep(5)
    validate_repose(module, changed, untouched)


def validate_repose(module, changed, untouched):
    success = []
    error = []
    timeout = []

    if check_if_repose_started():
        success = dict(
            pid=started_repose_id(),
            status='STARTED'
        )
    else:
        error = dict(
            status='FAILED'
        )

    results = {
        'changed': changed,
        'action': 'start',
        'pid': started_repose_id(),
        'success': success,
        'error': error,
        'timeout': timeout,
        'untouched': untouched
    }

    if error:
        results['msg'] = 'Failed to build repose'

    if 'msg' in results:
        module.fail_json(**results)
    else:
        module.exit_json(**results)


def delete(module, wait, wait_timeout):
    changed = False
    pid = started_repose_id()

    try:
        stop_repose_id(module, pid)
    except Exception, e:
        module.fail_json(msg=e.message)
    else:
        changed = True

    # If requested, wait for server deletion
    if wait:
        end_time = time.time() + wait_timeout
        infinite = wait_timeout == 0
        while infinite or time.time() < end_time:
            if started_repose_id():
                time.sleep(5)
            else:
                break

    if check_if_repose_started():
        error = dict(
            status='FAILED'
        )
    else:
        success = dict(
            pid=started_repose_id(),
            status='STARTED'
        )

    results = {
        'changed': changed,
        'action': 'delete',
        'success': success,
        'error': error
    }

    if error:
        results['msg'] = 'Failed to delete repose'

    if 'msg' in results:
        module.fail_json(**results)
    else:
        module.exit_json(**results)


# repose module
def repose(module, state, release, git_build, git_repo, git_branch,
           wait, wait_timeout):
    # act on the state
    if state == 'present':
        # check if git_build is set to true
        if git_build:
            # try to pull from git_repo/git_branch
            build_with_git(module, git_repo, git_branch, wait, wait_timeout)
            pass
        else:
            # build release
            # first get the operating system to either build via deb or rpm
            (package, _, _) = platform.linux_distribution()
            if release:
                build_with_release(module, release, package,
                                   wait, wait_timeout)
            else:
                build_with_git(module, git_repo, git_branch, wait,
                               wait_timeout)

    elif state == 'absent':
        delete(module, wait, wait_timeout)


# this is the starting point of the module!
def main():
    # get argument specifications
    argument_spec = dict()
    argument_spec.update(
        dict(
            release=dict(),
            git_build=dict(default=False, type='bool'),
            git_repo=dict(
                default='https://github.com/rackerlabs/repose'),
            git_branch=dict(default='master'),
            state=dict(default='present', choices=['present', 'absent']),
            wait=dict(default=False, type='bool'),
            wait_timeout=dict(default=300),
        )
    )

    module = AnsibleModule(
        argument_spec=argument_spec
    )

    release = module.params.get('release')
    git_build = module.params.get('git_build')
    git_repo = module.params.get('git_repo')
    git_branch = module.params.get('git_branch')
    state = module.params.get('state')
    wait = module.params.get('wait')
    wait_timeout = int(module.params.get('wait_timeout'))

    repose(module, state, release, git_build, git_repo, git_branch,
           wait, wait_timeout)


# import module snippets
from ansible.module_utils.basic import *

### invoke the module
main()
