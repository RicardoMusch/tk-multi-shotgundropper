"""
A Shotgun Toolkit Application that enables dropping entities from the browser.
"""
import re

from tank.platform import Application


class DropEventStatus(object):
    """
    Enum class to capture drop event states
    """
    #: The event was handled and the application should to not do anything else.
    HANDLED = 0
    #: The event was not handled and the application should try to what it is configured to do by default.
    NOT_HANDLED = 1


class ShotgunDrop(Application):
    """
    A Shotgun Toolkit Application that enables dropping entities from the browser.
    """
    MAYA_DROP_CALLBACK = None

    def init_app(self):
        if self.engine.name == 'tk-nuke':
            self.register_drop_event_nuke()
        elif self.engine.name == 'tk-maya':
            self.register_drop_event_maya()

    def destroy_app(self):
        if self.engine.name == 'tk-nuke':
            self.unregister_drop_event_nuke()
        elif self.engine.name == 'tk-maya':
            self.unregister_drop_event_maya()

    def register_drop_event_nuke(self):
        """
        Register the drop event to Nuke
        """
        import nukescripts
        nukescripts.addDropDataCallback(self.nuke_drop)

    def unregister_drop_event_nuke(self):
        """
        Remove the drop event when the app is destroyed
        """
        import nukescripts
        index = nukescripts.drop._gDropDataCallbacks.index(self.nuke_drop)
        nukescripts.drop._gDropDataCallbacks.pop(index)

    def register_drop_event_maya(self):
        """
        Register the drop event to Maya.
        """
        import maya.OpenMayaUI as OpenMayaUI

        class ExternalDropCallback(OpenMayaUI.MExternalDropCallback):

            def __init__(self, callback):
                self.callback = callback
                super(ExternalDropCallback, self).__init__()

            def externalDropCallback(self, doDrop, controlName, data):
                if doDrop and data.hasText():
                    # Key modifiers
                    shift = data.keyboardModifiers() & OpenMayaUI.MExternalDropData.kShiftModifier
                    ctrl = data.keyboardModifiers() & OpenMayaUI.MExternalDropData.kControlModifier
                    alt = data.keyboardModifiers() & OpenMayaUI.MExternalDropData.kAltModifier

                    text = data.text()

                    status = self.callback(text, controlName, ctrl, shift, alt)

                    if status == DropEventStatus.HANDLED:
                        # Let Maya know we handled the event.
                        return OpenMayaUI.MExternalDropCallback.kNoMayaDefaultAndAccept
                # We did not handle the event. -> Let Maya do its default thing.
                return OpenMayaUI.MExternalDropCallback.kMayaDefault

        self.MAYA_DROP_CALLBACK = ExternalDropCallback(self.maya_drop)
        OpenMayaUI.MExternalDropCallback.addCallback(self.MAYA_DROP_CALLBACK)

    def unregister_drop_event_maya(self):
        """
        Remove the drop event when the app is destroyed.
        """
        import maya.OpenMayaUI as OpenMayaUI
        OpenMayaUI.MExternalDropCallback.removeCallback(self.MAYA_DROP_CALLBACK)

    def nuke_drop(self, mime_type, text):
        """
        The actual drop function that will be called by Nuke when a drop event happens.

        :param str mime_type:
        :param str text:
        :return:
        """
        import nuke
        self.logger.debug('Drop Event captured: MIME type: "{}"  text: "{}"'.format(mime_type, text))

        if not mime_type == 'text/plain' or not text.startswith(self.tank.shotgun_url):
            self.logger.debug('Ignore event, because it does not come from Shotgun.')
            return  # return None when we do not handle the event.

        sg_type, sg_id = self.extract_entity_data(text)
        if sg_type is None:
            self.logger.debug('Could not extract entity information from URL "{}".'.format(text))
            nuke.message('Your dropped URL "{}" does not contain enough information to be processed. '
                         'If you think this is wrong please contact the pipeline department.'.format(text))
        else:
            self.logger.debug('Determined entity: {} {}'.format(sg_type, sg_id))

            # query all available fields for the dropped entity
            sg_entity_fields = self.shotgun.schema_field_read(sg_type, project_entity=self.context.project)
            sg_entity = self.shotgun.find_one(sg_type,
                                              [['id', 'is', sg_id]],
                                              sg_entity_fields.keys())

            publish_action_mappings = self.get_setting('action_mappings')

            try:
                # pass it on to the "determine_drop_action" hook
                result = self.execute_hook_method('determine_drop_action_hook',
                                                  'determine_drop_action',
                                                  sg_entity=sg_entity,
                                                  publish_action_mappings=publish_action_mappings,
                                                  params={})
            except:
                self.logger.exception('Error during "determine_drop_action" hook execution.')
                nuke.message('There was an error during your drop action. '
                             'Please contact the pipeline department.')
                return True

            if result is not None:
                try:
                    self.execute_hook_method('actions_hook',
                                             'execute_action',
                                             name=result['name'],
                                             params=result['params'],
                                             sg_publish_data=result['sg_publish_data'])
                except:
                    self.logger.exception('Error during "actions" hook execution.')
                    nuke.message('There was an error during your drop action. '
                                 'Please contact the pipeline department.')

        return True  # return True to let Nuke know we handled the event.

    def maya_drop(self, text, gui_widget, ctrl, shift, alt):
        """
        The actual drop function that will be called by Maya when a drop event happens.

        :param str text: The dropped URL
        :param str gui_widget: The name of the GUI widget that was dropped on.
        :param bool ctrl: Whether "CTRL" was pressed.
        :param bool shift: Whether "SHIFT" was pressed.
        :param bool alt: Whether "ALT" was pressed.
        :return: The status of the drop event. Whether it was handled or not.
        :rtype: int
        """
        import maya.cmds as cmds
        self.logger.debug('Drop Event captured: text: "{}"'.format(text))

        if not text.startswith(self.tank.shotgun_url):
            self.logger.debug('Ignore event, because it does not come from Shotgun.')
            return DropEventStatus.NOT_HANDLED

        sg_type, sg_id = self.extract_entity_data(text)
        if sg_type is None:
            self.logger.debug('Could not extract entity information from URL "{}".'.format(text))
            cmds.confirmDialog(title='Not enough information',
                               message='Your dropped URL "{}" does not contain enough information to be processed.'
                                       ''.format(text),
                               button=['Ok'])
        else:
            self.logger.debug('Determined entity: {} {}'.format(sg_type, sg_id))

            # query all available fields for the dropped entity
            sg_entity_fields = self.shotgun.schema_field_read(sg_type, project_entity=self.context.project)
            sg_entity = self.shotgun.find_one(sg_type,
                                              [['id', 'is', sg_id]],
                                              sg_entity_fields.keys())

            publish_action_mappings = self.get_setting('action_mappings')

            try:
                # pass it on to the "determine_drop_action" hook
                result = self.execute_hook_method('determine_drop_action_hook',
                                                  'determine_drop_action',
                                                  sg_entity=sg_entity,
                                                  publish_action_mappings=publish_action_mappings,
                                                  params={'gui_widget': gui_widget,
                                                          'ctrl': ctrl,
                                                          'shift': shift,
                                                          'alt': alt})
            except:
                self.logger.exception('Error during "determine_drop_action" hook execution.')
                cmds.confirmDialog(title='Error',
                                   message='There was an error during your drop action. '
                                           'Please contact the pipeline department.',
                                   icon='warning',
                                   button=['Ok'])
                return DropEventStatus.HANDLED

            if result is not None:
                try:
                    self.execute_hook_method('actions_hook',
                                             'execute_action',
                                             name=result['name'],
                                             params=result['params'],
                                             sg_publish_data=result['sg_publish_data'])
                except:
                    self.logger.exception('Error during "actions" hook execution.')
                    cmds.confirmDialog(title='Error',
                                       message='There was an error during your drop action. '
                                               'Please contact the pipeline department.',
                                       icon='warning',
                                       button=['Ok'])
        return DropEventStatus.HANDLED

    def extract_entity_data(self, url):
        """
        :param str url: The full URL that was send.
        :return: The extracted shotgun entity type and ID. Or None if nothing could be extracted.
        :rtype: tuple[str|None,int|None]
        """
        escaped_shotgun_url = re.escape(self.tank.shotgun_url)

        # URL from a Shotgun Website
        match = re.match(r'{}/detail/(\w+)/(\d+)'.format(escaped_shotgun_url), url)
        if match:
            return match.group(1), int(match.group(2))

        # URL out of an email
        match = re.match(r'{}/page/email_link\?entity_id=(\d+)&entity_type=(\w+)'.format(escaped_shotgun_url), url)
        if match:
            return match.group(2), int(match.group(1))

        # URL from the browser address field
        match = re.match(r'{}/page/\d+#(\w+)_(\d+)'.format(escaped_shotgun_url), url)
        if match:
            return match.group(1), int(match.group(2))

        return None, None
