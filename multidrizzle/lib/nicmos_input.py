#
#   Authors: Christopher Hanley, David Grumm
#   Program: nicmos_input.py
#   Purpose: Class used to model NICMOS specific instrument data.
#   History:
#           Version 0.1.0, ----------- Created
#           Version 0.1.1 09/15/04 -- Modified the setInstrumentParameters to treat
#               a user cr bit input value of zero as a None.  This allows the
#               user to turn off the DQ array update during the Driz_CR step. -- CJH
#           Version 0.1.2 09/20/04 -- Set the default crbit value for NICMOS to 4096 -- CJH.
#           Version 0.2.0 11/03/04 -- Modified the updateMDRIZSKY method to deal with
#               input data with EXPTIME = 0.  For that case, MDRIZSKY will be set to a
#               value of 0. -- CJH
#           Version 1.0.0 01/18/05 -- Updated converte2electrons and updateMDRIZSKY to work
#               with NICMOS data in both units of counts and counts/second           
#           Version 1.1.0 06/02/05 -- Calculates direction of CTE tail for cosmic rays
#               (not needed for NICMOS)
__version__ = '1.1.0'

import pydrizzle
from pydrizzle import fileutil
import numarray as N

from input_image import InputImage


class NICMOSInputImage (InputImage):

    SEPARATOR = '_'

    def __init__(self, input,dqname,platescale,memmap=1):
        InputImage.__init__(self,input,dqname,platescale,memmap=1)
        
        # define the cosmic ray bits value to use in the dq array
        self.cr_bits_value = 4096
        self.platescale = platescale
        
        # Effective gain to be used in the driz_cr step.  Since the
        # NICMOS images have already been converted to electrons the 
        # effective gain is 1.
        self._effGain = 1
 
        # no cte correction for NICMOS so set cte_dir=0.
        print('\nWARNING: No cte correction will be made for this NICMOS data.\n')
        self.cte_dir = 0   
        
        
    def setInstrumentParameters(self, instrpars, pri_header):
        """ This method overrides the superclass to set default values into
            the parameter dictionary, in case empty entries are provided.
        """
        if self._isNotValid (instrpars['gain'], instrpars['gnkeyword']):
            instrpars['gnkeyword'] = 'ADCGAIN'
        if self._isNotValid (instrpars['rdnoise'], instrpars['rnkeyword']):
            instrpars['rnkeyword'] = None
        if self._isNotValid (instrpars['exptime'], instrpars['expkeyword']):
            instrpars['expkeyword'] = 'EXPTIME'
        if instrpars['crbit'] == None:
            instrpars['crbit'] = self.cr_bits_value
   
        self._gain      = self.getInstrParameter(instrpars['gain'], pri_header,
                                                 instrpars['gnkeyword'])
        self._rdnoise   = self.getInstrParameter(instrpars['rdnoise'], pri_header,
                                                 instrpars['rnkeyword'])
        self._exptime   = self.getInstrParameter(instrpars['exptime'], pri_header,
                                                 instrpars['expkeyword'])
        self._crbit     = instrpars['crbit']

        if self._gain == None or self._exptime == None:
            print 'ERROR: invalid instrument task parameter'
            raise ValueError

        # We need to treat Read Noise as a special case since it is 
        # not populated in the NICMOS primary header
        if (instrpars['rnkeyword'] != None):
            self._rdnoise   = self.getInstrParameter(instrpars['rdnoise'], pri_header,
                                                     instrpars['rnkeyword'])                                                 
        else:
            self._rdnoise = None


        # We need to determine if the user has used the default readnoise/gain value
        # since if not, they will need to supply a gain/readnoise value as well        
        
        usingDefaultReadnoise = False
        if (instrpars['rnkeyword'] == None):
            usingDefaultReadnoise = True

            
        # Set the default readnoise values based upon the amount of user input given.
        
        # User supplied no readnoise information
        if usingDefaultReadnoise:
            # Set the default gain and readnoise values
            self._setchippars()

    def _setchippars(self):
        self._setDefaultReadnoise()
                
    def updateMDRIZSKY(self,filename=None):
    
        if (filename == None):
            filename = self.name
            
        try:
            _handle = fileutil.openImage(filename,mode='update',memmap=0)
        except:
            raise IOError, "Unable to open %s for sky level computation"%filename
        try:
        
            # Get the exposure time for the image.  If the exposure time of the image
            # is 0, set the MDRIZSKY value to 0.  Otherwise update the MDRIZSKY value
            # in units of counts per second.
            if (self.getExpTime() == 0.0):
                str =  "*******************************************\n"
                str += "*                                         *\n"
                str += "* ERROR: Image EXPTIME = 0.               *\n"
                str += "* MDRIZSKY header value cannot be         *\n"
                str += "* converted to units of 'counts/s'        *\n"
                str += "* MDRIZSKY will be set to a value of '0'  *\n"
                str += "*                                         *\n"
                str =  "*******************************************\n"
                _handle[0].header['MDRIZSKY'] = 0
                print str
            else:
                # Assume the MDRIZSKY keyword is in the primary header.  Try to update
                # the header value
                try:
                    # We need to handle the updates of the header for data in 
                    # original units of either counts per second or counts
                    if (_handle[0].header['UNITCORR'].strip() == 'PERFORM'):
                        print "Updating MDRIZSKY in %s with %f / %f / %f = %f"%(filename,
                                self.getSubtractedSky(),
                                self.getGain(), 
                                self.getExpTime(),
                                self.getSubtractedSky() / self.getGain() / self.getExpTime()
                                )
                        _handle[0].header['MDRIZSKY'] = self.getSubtractedSky() / self.getGain() / self.getExpTime()
                    else:
                        print "Updating MDRIZSKY in %s with %f / %f  = %f"%(filename,
                                self.getSubtractedSky(),
                                self.getGain(), 
                                self.getSubtractedSky() / self.getGain() 
                                )
                        _handle[0].header['MDRIZSKY'] = self.getSubtractedSky() / self.getGain() 
                        
                # The MDRIZSKY keyword was not found in the primary header.  Add the
                # keyword to the header and populate it with the subtracted sky value.
                except:
                    print "Cannot find keyword MDRIZSKY in %s to update"%filename
                    if (_handle[0].header['UNITCORR'].strip() == 'PERFORM'):
                        print "Adding MDRIZSKY keyword to primary header with value %f"%(self.getSubtractedSky()/self.getGain()/self.getExpTime())
                        _handle[0].header.update('MDRIZSKY',self.getSubtractedSky()/self.getGain()/self.getExpTime(), 
                            comment="Sky value subtracted by Multidrizzle")
                    else:
                        print "Adding MDRIZSKY keyword to primary header with value %f"%(self.getSubtractedSky()/self.getGain())
                        _handle[0].header.update('MDRIZSKY',self.getSubtractedSky()/self.getGain(), 
                            comment="Sky value subtracted by Multidrizzle")
                    
        finally:
            _handle.close()

    def doUnitConversions(self):
        self._convert2electrons()

    def _convert2electrons(self):
        # Image information
        __handle = fileutil.openImage(self.name,mode='update',memmap=0)
        __sciext = fileutil.getExtn(__handle,extn=self.extn)        

        # Determine if Multidrizzle is in units of counts/second or counts
        #
        # Counts per second case
        if (__handle[0].header['UNITCORR'].strip() == 'PERFORM'):        
            # Multiply the values of the sci extension pixels by the gain.
            print "Converting %s from COUNTS/S to ELECTRONS"%(self.name)
            # If the exptime is 0 the science image will be zeroed out.
            conversionFactor = (self.getExpTime() * self.getGain()) 
        # Counts case
        else:
            # Multiply the values of the sci extension pixels by the gain.
            print "Converting %s from COUNTS to ELECTRONS"%(self.name)
            # If the exptime is 0 the science image will be zeroed out.
            conversionFactor = (self.getExpTime()) 
        N.multiply(__sciext.data,conversionFactor,__sciext.data)        
        
        __handle.close()
        del __handle
        del __sciext

class NIC1InputImage(NICMOSInputImage):

    def __init__(self, input, dqname, platescale, memmap=1):
        NICMOSInputImage.__init__(self,input,dqname,platescale,memmap=1)
        self.instrument = 'NICMOS/1'
        self.full_shape = (256,256)
        self.platescale = platescale

    def _setDefaultReadnoise(self):
        self._rdnoise = 27.5

class NIC2InputImage(NICMOSInputImage):
    def __init__(self, input, dqname, platescale, memmap=1):
        NICMOSInputImage.__init__(self,input,dqname,platescale,memmap=1)
        self.instrument = 'NICMOS/2'
        self.full_shape = (256,256)
        self.platescale = platescale

    def _setDefaultReadnoise(self):
        self._rdnoise = 27.5

class NIC3InputImage(NICMOSInputImage):
    def __init__(self, input, dqname, platescale, memmap=1):
        NICMOSInputImage.__init__(self,input,dqname,platescale,memmap=1)
        self.instrument = 'NICMOS/3'
        self.full_shape = (256,256)
        self.platescale = platescale

    def _setDefaultReadnoise(self):
        self._rdnoise = 29.9
