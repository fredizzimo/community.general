#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2014, Gabe Mulley <gabe.mulley@gmail.com>
# Copyright: (c) 2015, David Wittman <dwittman@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


DOCUMENTATION = r'''
---
module: alternatives
short_description: Manages alternative programs for common commands
description:
    - Manages symbolic links using the 'update-alternatives' tool.
    - Useful when multiple programs are installed but provide similar functionality (e.g. different editors).
author:
    - David Wittman (@DavidWittman)
    - Gabe Mulley (@mulby)
options:
  name:
    description:
      - The generic name of the link.
    type: str
    required: true
  path:
    description:
      - The path to the real executable that the link should point to.
    type: path
    required: true
  link:
    description:
      - The path to the symbolic link that should point to the real executable.
      - This option is always required on RHEL-based distributions. On Debian-based distributions this option is
        required when the alternative I(name) is unknown to the system.
    type: path
  priority:
    description:
      - The priority of the alternative.
    type: int
    default: 50
  slaves:
    description:
      - A list of slaves
      - Each slave needs a name, a link and a path parameter
    type: list
    elements: dict

requirements: [ update-alternatives ]
'''

EXAMPLES = r'''
- name: Correct java version selected
  community.general.alternatives:
    name: java
    path: /usr/lib/jvm/java-7-openjdk-amd64/jre/bin/java

- name: Alternatives link created
  community.general.alternatives:
    name: hadoop-conf
    link: /etc/hadoop/conf
    path: /etc/hadoop/conf.ansible

- name: Make java 32 bit an alternative with low priority
  community.general.alternatives:
    name: java
    path: /usr/lib/jvm/java-7-openjdk-i386/jre/bin/java
    priority: -10

- name: keytool is a slave of java
  community.general.alternatives:
    name: java
    link: /usr/bin/java
    path: /usr/lib/jvm/java-7-openjdk-amd64/jre/bin/java
    slaves:
      - name: keytool
        link: /usr/bin/keytool
        path: /usr/lib/jvm/java-7-openjdk-amd64/jre/bin/keytool
'''

import os
import re
import subprocess

from ansible.module_utils.basic import AnsibleModule


def get_current(module, bin, name, link):
    """Get the options and the currently set value for the named alternative.

    If `link` is not specified, this value will be retrieved from the
    alternatives database.

    Returns a tuple of currently set value, possible options, and link path."""
    current_path = None
    all_alternatives = []

    # Run `update-alternatives --display <name>` to find existing alternatives
    (rc, display_output, dummy) = module.run_command(
        ['env', 'LC_ALL=C', bin, '--display', name]
    )

    if rc == 0:
        # Alternatives already exist for this link group
        # Parse the output to determine the current path of the symlink and
        # available alternatives
        current_path_regex = re.compile(r'^\s*link currently points to (.*)$',
                                        re.MULTILINE)
        alternative_regex = re.compile(r'^(\/.*)\s-\s(?:family\s\S+\s)?priority', re.MULTILINE)

        match = current_path_regex.search(display_output)
        if match:
            current_path = match.group(1)
        all_alternatives = alternative_regex.findall(display_output)

        if not link:
            # Read the current symlink target from `update-alternatives --query`
            # in case we need to install the new alternative before setting it.
            #
            # This is only compatible on Debian-based systems, as the other
            # alternatives don't have --query available
            rc, query_output, dummy = module.run_command(
                ['env', 'LC_ALL=C', bin, '--query', name]
            )
            if rc == 0:
                for line in query_output.splitlines():
                    if line.startswith('Link:'):
                        link = line.split()[1]
                        break

    return current_path, all_alternatives, link


def set_alternative(module, bin, name, path, link, priority, slaves,
                    current_path, all_alternatives):
    """Set the current named alternative to the specified path.

    If not present in the currently configured alternatives, the requested
    alternative will be added with the specified priority.  The `link`
    parameter must be provided in this instance."""
    if current_path != path:
        if module.check_mode:
            module.exit_json(changed=True, current_path=current_path)
        try:
            # install the requested path if necessary
            if path not in all_alternatives:
                if not os.path.exists(path):
                    module.fail_json(msg="Specified path %s does not exist" % path)
                if not link:
                    module.fail_json(msg="Needed to install the alternative, "
                                     "but unable to do so as we are missing the link")

                cmd = [bin, '--install', link, name, path, str(priority)]
                if slaves:
                    slaves = map(lambda slave: ['--slave', slave['link'], slave['name'], slave['path']], slaves)
                    cmd += [item for sublist in slaves for item in sublist]

                module.run_command(
                    cmd,
                    check_rc=True
                )

            # select the requested path
            module.run_command(
                [bin, '--set', name, path],
                check_rc=True
            )

            module.exit_json(changed=True)
        except subprocess.CalledProcessError as cpe:
            module.fail_json(msg=str(dir(cpe)))
    else:
        module.exit_json(changed=False)


def main():
    """Main module entrypoint"""
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(type='str', required=True),
            path=dict(type='path', required=True),
            link=dict(type='path'),
            priority=dict(type='int', default=50),
            slaves=dict(type='list', elements='dict'),
        ),
        supports_check_mode=True,
    )

    params = module.params
    name = params['name']
    path = params['path']
    link = params['link']
    priority = params['priority']
    slaves = params['slaves']

    UPDATE_ALTERNATIVES = module.get_bin_path('update-alternatives', True)
    (current_path, all_alternatives, link) = get_current(
        module, UPDATE_ALTERNATIVES, name, link)

    set_alternative(module, UPDATE_ALTERNATIVES, name, path, link, priority, slaves,
                    current_path, all_alternatives)


if __name__ == '__main__':
    main()
