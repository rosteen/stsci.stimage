""" Main module for the ConfigObj version of the EPAR task editor

$Id$
"""

import configobj, os, tkMessageBox
import cfgpars, editpar, filedlg
from cfgpars import APP_NAME


# Starts a GUI session
def epar(theTask, parent=None, isChild=0, loadOnly=False):
    if loadOnly:
        return cfgpars.getObjectFromTaskArg(theTask)
    else:
        dlg = ConfigObjEparDialog(theTask, parent, isChild)
        if dlg.canceled():
            return None
        else:
            return dlg.getTaskParsObj()


# Main class
class ConfigObjEparDialog(editpar.EditParDialog):

    def __init__(self, theTask, parent=None, isChild=0,
                 title=APP_NAME, childList=None):

        # Init base - calls _setTaskParsObj(), sets self.taskName, etc
        editpar.EditParDialog.__init__(self, theTask, parent, isChild,
                                       title, childList,
                                       resourceDir=cfgpars.getAppDir())
        # We don't return from this until the GUI is closed


    def _overrideMasterSettings(self):
        """ Override so that we can run in a different mode. """
        cod = self._getGuiSettings()
        self._useSimpleAutoClose  = False # is a fundamental issue here
        self._showExtraHelpButton = False
        self._saveAndCloseOnExec  = cod.get('saveAndCloseOnExec', False)
        self._showHelpInBrowser   = cod.get('showHelpInBrowser', False)
        self._optFile             = APP_NAME.lower()+".optionDB"


    def _preMainLoop(self):
        """ Override so that we can do some things right before activating. """
        # Put the fname in the title. EditParDialog doesn't do this by default
        self.updateTitle(self._taskParsObj.filename)


    def _doActualSave(self, filename, comment):
        """ Override this so we can handle case of file not writable. """
        try:
            rv=self._taskParsObj.saveParList(filename=filename,comment=comment)
            return rv
        except IOError:
            # User does not have privs to write to this file. Get name of local
            # choice and try to use that.
            mine = self._rcDir+os.sep+self._taskParsObj.getName()+'.cfg'
            # Tell them the context is changing, and where we are saving
            msg = 'Installed config file for task "'+ \
                  self._taskParsObj.getName()+'" is unwritable. \n'+ \
                  'Values will be saved to: \n\n\t"'+mine+'".'
            tkMessageBox.showwarning(message=msg, title="File unwritable!")
            # Try saving their copy
            rv=self._taskParsObj.saveParList(filename=mine, comment=comment)
            # Treat like a save-as
            self._saveAsPostSave_Hook(mine)
            return rv


    def _saveAsPostSave_Hook(self, fnameToBeUsed_UNUSED):
        """ Override this so we can update the title bar. """
        self.updateTitle(self._taskParsObj.filename) # _taskParsObj is correct


    # Always allow the Open button ?
    def _showOpenButton(self): return True


    # Employ an edited callback for a given item?
    def _defineEditedCallbackObjectFor(self, parScope, parName):
        """ Override to allow us to use an edited callback. """

        # We know that the _taskParsObj is a ConfigObjPars
        triggerStr = self._taskParsObj.getTriggerStr(parScope, parName)

        # Some items will have a trigger, but likely most won't
        if triggerStr:
            return self
        else:
            return None


    def edited(self, scope, name, lastSavedVal, newVal):
        """ This is the callback function invoked when an item is edited.
            This is only called for those items which were previously
            specified to use this mechanism.  We do not turn this on for
            all items because the performance might be prohibitive. """
        # the print line is a stand-in
        triggerStr = self._taskParsObj.getTriggerStr(scope, name)
        # call triggers in a general way, not directly here # !!!
        if triggerStr.find('_section_switch_')>=0:
            state = str(newVal).lower() in ('on','yes','true')
            self._toggleSectionActiveState(scope, state, (name,))
        else:
            print "val: "+newVal+", trigger: "+triggerStr
    

    def _setTaskParsObj(self, theTask):
        """ Overridden version for ConfigObj. theTask can be either
            a .cfg file name or a ConfigObjPars object. """
        self._taskParsObj = cfgpars.getObjectFromTaskArg(theTask)


    def _getSaveAsFilter(self):
        """ Return a string to be used as the filter arg to the save file
            dialog during Save-As. """
        filt = '*.cfg'
        if 'UPARM_AUX' in os.environ:
            upx = os.environ['UPARM_AUX']
            if len(upx) > 0:  filt = upx+"/*.cfg" 
        return filt


    # OPEN: load parameter settings from a user-specified file
    def pfopen(self, event=None):
        """ Load the parameter settings from a user-specified file. """

        # could use Tkinter's FileDialog, but this one is prettier
        fd = filedlg.PersistLoadFileDialog(self.top, "Load Config File",
                                           self._getSaveAsFilter())
        if fd.Show() != 1:
            fd.DialogCleanup()
            return
        fname = fd.GetFileName()
        fd.DialogCleanup()
        if fname == None: return # canceled

        # load it into a tmp object
        tmpObj = cfgpars.ConfigObjPars(fname)

        # check it to make sure it is a match
        if not self._taskParsObj.isSameTaskAs(tmpObj):
            msg = 'The current task is "'+self._taskParsObj.getName()+ \
                  '", but the selected file is for task "'+tmpObj.getName()+ \
                  '".  This file was not loaded.'
            tkMessageBox.showerror(message=msg,
                title="Error in "+os.path.basename(fname))
            return

        # Set the GUI entries to these values (let the user Save after)
        newParList = tmpObj.getParList()
        try:
            self.setAllEntriesFromParList(newParList)
        except editpar.UnfoundParamError, pe:
            tkMessageBox.showwarning(message=pe.message, title="Error in "+\
                                     os.path.basename(fname))

        # This new fname is our current context
        self.updateTitle(fname)
        self._taskParsObj.filename = fname # !! maybe try setCurrentContext() ?


    def unlearn(self, event=None):
        """ Override this so that we can set to default values our way. """
        self._setToDefaults()


    def _setToDefaults(self):
        """ Load the default parameter settings into the GUI. """

        # Create an empty object, where every item is set to it's default value
        try:
            tmpObj = cfgpars.ConfigObjPars(self._taskParsObj.filename,
                                           setAllToDefaults=True)
            print "Loading default "+self.taskName+" values via: "+ \
                  os.path.basename(tmpObj._original_configspec)
        except Exception, ex:
            msg = "Error Determining Defaults"
            tkMessageBox.showerror(message=msg+'\n\n'+ex.message,
                                   title="Error Determining Defaults")
            return

        # Set the GUI entries to these values (let the user Save after)
        newParList = tmpObj.getParList()
        try:
            self.setAllEntriesFromParList(newParList)
        except editpar.UnfoundParamError, pe:
            tkMessageBox.showerror(message=pe.message,
                                   title="Error Setting to Default Values")

    def _getGuiSettings(self):
        """ Return a dict (ConfigObj) of all user settings found in rcFile. """
        # Put the settings into a ConfigObj dict (don't use a config-spec)
        rcFile = self._rcDir+os.sep+APP_NAME.lower()+'.cfg'
        if os.path.exists(rcFile):
            return configobj.ConfigObj(rcFile, unrepr=True)
            # unrepr: for simple types, eliminates need for .cfgspc
        else:
            return {}


    def _saveGuiSettings(self):
        """ The base class doesn't implement this, so we will - save settings
        (only GUI stuff, not task related) to a file. """
        # Put the settings into a ConfigObj dict (don't use a config-spec)
        rcFile = self._rcDir+os.sep+APP_NAME.lower()+'.cfg'
        #
        if os.path.exists(rcFile): os.remove(rcFile)
        co = configobj.ConfigObj(rcFile)
        self._showHelpInBrowser = self.helpChoice.get() != "WINDOW"
        co['showHelpInBrowser']  = self._showHelpInBrowser
        co['saveAndCloseOnExec'] = self._saveAndCloseOnExec
        co.initial_comment = ['This file is automatically generated by '+\
                              APP_NAME+'.  Do not edit.']
        co.final_comment = [''] # ensure \n at EOF
        co.unrepr = True # for simple types, eliminates need for .cfgspc
        co.write()

