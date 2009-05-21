#
#   Authors: Christopher Hanley, David Grumm, Megan Sosey
#   Program: nicmos_input.py
#   Purpose: Class used to model NICMOS specific instrument data.

from pytools import fileutil
from nictools import readTDD
import numpy as np
from imageObject import imageObject
from staticMask import constructFilename

class NICMOSInputImage(imageObject):

    SEPARATOR = '_'

    def __init__(self, filename=None):
        imageObject.__init__(self,filename)
        
        # define the cosmic ray bits value to use in the dq array
        self.cr_bits_value = 4096

        # Detector parameters, nic only has 1 detector in each file
        self.full_shape = (256,256)
        self._instrument=self._image['PRIMARY'].header["INSTRUME"]
         
        for chip in range(1,self._numchips+1,1):
            self._image[self.scienceExt,chip].cte_dir = 0   #no correction for nicmos
       
        self._effGain = 1. #get the specific gain from the detector subclass
            
    def _assignSignature(self, chip):
        """assign a unique signature for the image based 
           on the  instrument, detector, chip, and size
           this will be used to uniquely identify the appropriate
           static mask for the image
           
           this also records the filename for the static mask to the outputNames dictionary
           
        """
        sci_chip = self._image[self.scienceExt,chip]
        ny=sci_chip._naxis1
        nx=sci_chip._naxis2
        detnum = sci_chip.detnum
        instr=self._instrument
        
        sig=(instr+str(self._detector),(nx,ny),int(detnum)) #signature is a tuple
        sci_chip.signature=sig #signature is a tuple
        filename=constructFilename(sig)
        sci_chip.outputNames["staticMask"]=filename #this is the name of the static mask file
     

    def doUnitConversions(self):
        """convert the data to electrons
        
        This converts all science data extensions and saves
        the results back to disk. We need to make sure
        the data inside the chips already in memory is altered as well
        
        """
        

         # Image information 
        _handle = fileutil.openImage(self._filename,mode='update',memmap=0) 

        for det in range(1,self._numchips,1):

            chip=self._image[self.scienceExt,det]
            
            if chip._gain != None:

                # Multiply the values of the sci extension pixels by the gain. 
                print "Converting %s from COUNTS to ELECTRONS"%(self._filename) 

                # If the exptime is 0 the science image will be zeroed out. 
                np.multiply(_handle[self.scienceExt,det].data,chip._gain,_handle[self.scienceExt,det].data)
                chip.data=_handle[det].data

                # Set the BUNIT keyword to 'electrons'
                _handle[det].header.update('BUNIT','ELECTRONS')

                # Update the PHOTFLAM value
                photflam = _handle[det].header['PHOTFLAM']
                _handle[det].header.update('PHOTFLAM',(photflam/chip._gain))
                
                chip._effGain = 1.
            
            else:
                print "Invalid gain value for data, no conversion done"
                return ValueError

        # Close the files and clean-up
        _handle.close() 

        self._effGain = 1.


    def _setchippars(self):
        self._setDefaultReadnoise()
                
    def getflat(self):
        """

        Purpose
        =======
        Method for retrieving a detector's flat field.
        
        This method will return an array the same shape as the
        image.

        :units: cps

        """

        # The keyword for NICMOS flat fields in the primary header of the flt
        # file is FLATFILE.  This flat file is not already in the required 
        # units of electrons.
        
        filename = self._image["PRIMARY"].header['FLATFILE']
        
        try:
            handle = fileutil.openImage(filename,mode='readonly',memmap=0)
            hdu = fileutil.getExtn(handle,extn=self.grp)
            data = hdu.data[self.ltv2:self.size2,self.ltv1:self.size1]
        except:
            try:
                handle = fileutil.openImage(filename[5:],mode='readonly',memmap=0)
                hdu = fileutil.getExtn(handle,extn=self.grp)
                data = hdu.data[self.ltv2:self.size2,self.ltv1:self.size1]
            except:
                data = np.ones(self.image_shape,dtype=self.image_dtype)
                str = "Cannot find file "+filename+".  Treating flatfield constant value of '1'.\n"
                print str

        flat = (1.0/data) # The reference flat field is inverted

        return flat
        

    def getdarkcurrent(self):
        """
        
        Purpose
        =======
        Return the dark current for the NICMOS detectors.
        
        :units: cps
        
        """
                
        try:
            darkcurrent = self.header['exptime'] * self.darkrate
            
        except:
            str =  "#############################################\n"
            str += "#                                           #\n"
            str += "# Error:                                    #\n"
            str += "#   Cannot find the value for 'EXPTIME'     #\n"
            str += "#   in the image header.  NICMOS input      #\n"
            str += "#   images are expected to have this header #\n"
            str += "#   keyword.                                #\n"
            str += "#                                           #\n"
            str += "#Error occured in the NICMOSInputImage class#\n"
            str += "#                                           #\n"
            str += "#############################################\n"
            raise ValueError, str
        
        
        return darkcurrent
        
    def getdarkimg(self):
        """
        
        Purpose
        =======
        Return an array representing the dark image for the detector.
        
        :units: cps
        
        """

        # Read the temperature dependeant dark file.  The name for the file is taken from
        # the TEMPFILE keyword in the primary header.
        tddobj = readTDD.fromcalfile(self.name)

        if tddobj == None:
            return np.ones(self.full_shape,dtype=self.image_dtype)*self.getdarkcurrent()
        else:
            # Create Dark Object from AMPGLOW and Lineark Dark components
            darkobj = tddobj.getampglow() + tddobj.getlindark()
                        
            # Return the darkimage taking into account an subarray information available
            return darkobj[self.ltv2:self.size2,self.ltv1:self.size1]
 
    def isCountRate(self):
        """
        isCountRate: Method or IRInputObject used to indicate if the
        science data is in units of counts or count rate.  This method
        assumes that the keyword 'BUNIT' is in the header of the input
        FITS file.
        """
        
        if self.header.has_key('BUNIT'):       
            if self.header['BUNIT'].find("/") != -1:
                return True
        else:
            return False
        
    
class NIC1InputImage(NICMOSInputImage):

    def __init__(self, filename=None):
        NICMOSInputImage.__init__(self,filename)
        self._effGain = 1. #get the gain from the detector subclass        
        self._detector=self._image["PRIMARY"].header["CAMERA"]
        self.proc_unit = "native"
        
    def _getDarkRate(self):
        _darkrate = 0.08 #electrons/s
        if self.proc_unit == 'native':
            _darkrate = _darkrate / self._effGain # DN/s
        
        return _darkrate
        
    def _getDefaultReadnoise(self):
        """ this could be updated to calculate the readnoise from the NOISFILE            
        """
        _rdnoise = 26.0 # electrons
        if self.proc_unit == 'native':
            _rdnoise = _rdnoise / self._effGain # ADU
        
        return _rdnoise
        
    def setInstrumentParameters(self, instrpars):
        """ This method overrides the superclass to set default values into
            the parameter dictionary, in case empty entries are provided.
        """
        pri_header = self._image[0].header

        self.proc_unit = instrpars['proc_unit']

        if self._isNotValid (instrpars['gain'], instrpars['gnkeyword']):
            instrpars['gnkeyword'] = 'ADCGAIN' #gain has been hardcoded below
            
        if self._isNotValid (instrpars['rdnoise'], instrpars['rnkeyword']):
            instrpars['rnkeyword'] = None
        if self._isNotValid (instrpars['exptime'], instrpars['expkeyword']):
            instrpars['expkeyword'] = 'EXPTIME'
    
        for chip in self.returnAllChips(extname=self.scienceExt):

            chip._gain= 5.4 #measured gain
            
            chip._rdnoise   = self.getInstrParameter(instrpars['rdnoise'], pri_header,
                                                     instrpars['rnkeyword'])
            chip._exptime   = self.getInstrParameter(instrpars['exptime'], pri_header,
                                                     instrpars['expkeyword'])
                                                     
            if chip._gain == None or self._exptime == None:
                print 'ERROR: invalid instrument task parameter'
                raise ValueError

            # We need to treat Read Noise as a special case since it is 
            # not populated in the NICMOS primary header
            if chip._rdnoise == None:
                chip._rdnoise = self._getDefaultReadnoise()

            chip._darkrate=self._getDarkRate()
            
            chip._effGain = chip._gain
            self._assignSignature(chip.extnum) #this is used in the static mask, static mask name also defined here, must be done after outputNames
        
         
        # Convert the science data to electrons if specified by the user.  Each
        # instrument class will need to define its own version of doUnitConversions
        if self.proc_unit == "electrons":
            self.doUnitConversions()

        
        # Convert the science data to electrons if specified by the user.  Each
        # instrument class will need to define its own version of doUnitConversions
        if self.proc_unit == "electrons":
            self.doUnitConversions()



class NIC2InputImage(NICMOSInputImage):
    def __init__(self,filename=None):
        NICMOSInputImage.__init__(self,filename)
        self._effGain=1. #measured
        self._detector=self._image["PRIMARY"].header["CAMERA"]
        self.proc_unit = "native"
        
    def _getDarkRate(self):
        _darkrate = 0.08 #electrons/s
        if self.proc_unit == 'native':
            _darkrate = _darkrate / self._effGain # DN/s
    
        return _darkrate
        
    def _getDefaultReadnoise(self):
        _rdnoise = 26.0 #electrons
        if self.proc_unit == 'native':
            _rdnoise = _rdnoise/self._effGain #ADU

        return _rdnoise

    def setInstrumentParameters(self, instrpars):
        """ This method overrides the superclass to set default values into
            the parameter dictionary, in case empty entries are provided.
        """
        pri_header = self._image[0].header

        self.proc_unit = instrpars['proc_unit']

        if self._isNotValid (instrpars['gain'], instrpars['gnkeyword']):
            instrpars['gnkeyword'] = 'ADCGAIN' #gain has been hardcoded below
            
        if self._isNotValid (instrpars['rdnoise'], instrpars['rnkeyword']):
            instrpars['rnkeyword'] = None
        if self._isNotValid (instrpars['exptime'], instrpars['expkeyword']):
            instrpars['expkeyword'] = 'EXPTIME'
    
        for chip in self.returnAllChips(extname=self.scienceExt):

            chip._gain= 5.4 #measured gain
            
            chip._rdnoise   = self.getInstrParameter(instrpars['rdnoise'], pri_header,
                                                     instrpars['rnkeyword'])
            chip._exptime   = self.getInstrParameter(instrpars['exptime'], pri_header,
                                                     instrpars['expkeyword'])
                                                     
            if chip._gain == None or self._exptime == None:
                print 'ERROR: invalid instrument task parameter'
                raise ValueError

            # We need to treat Read Noise as a special case since it is 
            # not populated in the NICMOS primary header
            if chip._rdnoise == None:
                chip._rdnoise = self._getDefaultReadnoise()

            chip._darkrate=self._getDarkRate()
            
            chip._effGain = chip._gain
            self._assignSignature(chip.extnum) #this is used in the static mask, static mask name also defined here, must be done after outputNames
        
         
        # Convert the science data to electrons if specified by the user.  Each
        # instrument class will need to define its own version of doUnitConversions
        if self.proc_unit == "electrons":
            self.doUnitConversions()


    def createHoleMask(self):
        """add in a mask for the coronographic hole to the general static pixel mask"""
        pass
        

class NIC3InputImage(NICMOSInputImage):
    def __init__(self,filename=None):
        NICMOSInputImage.__init__(self,filename)
        self._detector=self._image["PRIMARY"].header["CAMERA"] #returns 1,2,3
        self._effGain = 1.
        self.proc_unit = "native"
        
    def _getDarkRate(self):
        _darkrate = 0.15 #electrons/s
        if self.proc_unit == 'native':
            _darkrate = _darkrate/self._effGain #DN/s

        return _darkrate
        
    def _getDefaultReadnoise(self):
        _rdnoise = 29.0 # electrons
        if self.proc_unit == 'native':
            _rdnoise = _rdnoise/self._effGain #ADU

        return _rdnoise
        
    def setInstrumentParameters(self, instrpars):
        """ This method overrides the superclass to set default values into
            the parameter dictionary, in case empty entries are provided.
        """
        pri_header = self._image[0].header

        self.proc_unit = instrpars['proc_unit']

        if self._isNotValid (instrpars['gain'], instrpars['gnkeyword']):
            instrpars['gnkeyword'] = 'ADCGAIN'
        if self._isNotValid (instrpars['rdnoise'], instrpars['rnkeyword']):
            instrpars['rnkeyword'] = None
        if self._isNotValid (instrpars['exptime'], instrpars['expkeyword']):
            instrpars['expkeyword'] = 'EXPTIME'
    
        for chip in self.returnAllChips(extname=self.scienceExt):

            chip._gain= 6.5 #measured gain
            
            chip._rdnoise   = self.getInstrParameter(instrpars['rdnoise'], pri_header,
                                                     instrpars['rnkeyword'])
            chip._exptime   = self.getInstrParameter(instrpars['exptime'], pri_header,
                                                     instrpars['expkeyword'])
                                                     
            if chip._gain == None or self._exptime == None:
                print 'ERROR: invalid instrument task parameter'
                raise ValueError

            # We need to treat Read Noise as a special case since it is 
            # not populated in the NICMOS primary header
            if chip._rdnoise == None:
                chip._rdnoise = self._getDefaultReadnoise()

            chip._darkrate=self._getDarkRate()

            chip._effGain = chip._gain
            self._assignSignature(chip.extnum) #this is used in the static mask, static mask name also defined here, must be done after outputNames
        
         
        # Convert the science data to electrons if specified by the user.  Each
        # instrument class will need to define its own version of doUnitConversions
        if self.proc_unit == "electrons":
            self.doUnitConversions()

