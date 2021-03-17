# Copyright (c) 2015 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.
"""
Hook that loads defines all the available actions, broken down by publish type.
"""
import tank

HookBaseClass = tank.get_hook_baseclass()


class DetermineNukeDropAction(HookBaseClass):
    """
    The purpose of this hook is to determine the action that should be performed based on the dropped entity.
    """

    def determine_drop_action(self, sg_entity, publish_action_mappings, params):
        """
        :param dict sg_entity: The entity with _all_ fields that was dropped into Nuke.
        :param dict publish_action_mappings:
        :param dict params: Extra parameters from the app.
        """
        import nuke

        params['drag_and_dropped'] = True

        if 'PublishedFile' == sg_entity['type']:

            if sg_entity['project'].get('id') == self.parent.context.project['id']:
                published_file_type = sg_entity['published_file_type']['name']
                if published_file_type in publish_action_mappings:
                    return {'name': publish_action_mappings[published_file_type][0],
                            'params': params,
                            'sg_publish_data': sg_entity}
                else:
                    nuke.message('Dont know how to load "{}" publishes. Operation canceled.'
                                 ''.format(published_file_type))
            else:
                nuke.message('The Publish File you dropped does not belong to this project. '
                             'Operation canceled.')

        elif 'Version' == sg_entity['type']:

            if sg_entity['project'].get('id') == self.parent.context.project['id']:

                return {'name': 'drop_version',
                        'params': params,
                        'sg_publish_data': sg_entity}
            else:
                nuke.message('The Version you dropped does not belong to this project. Operation canceled.')

        elif 'Playlist' == sg_entity['type']:

            if sg_entity['project'].get('id') == self.parent.context.project['id']:

                return {'name': 'drop_playlist',
                        'params': params,
                        'sg_publish_data': sg_entity}
            else:
                nuke.message('The Playlist you dropped does not belong to this project. Operation canceled.')

        else:
            self.logger.debug('No drop action defined for this entity.')
            nuke.message('There is no drop action defined for {}s'.format(sg_entity['type']))
