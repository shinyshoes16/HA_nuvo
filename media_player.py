import functools
import logging
import re
import io
import serial
import string
import time
import asyncio
import datetime
from functools import wraps
from threading import RLock

_LOGGER = logging.getLogger(__name__)
#logging.basicConfig(format='%(asctime)s;%(levelname)s:%(message)s', level=logging.DEBUG)

'''
#Z0xPWRppp,SRCs,VOL-yy<CR>
'''
CONCERTO_PATTERN = re.compile('Z0(?P<zone>\d)'
                     'PWR(?P<power>ON|OFF),'
                     'SRC(?P<source>\d),'
                     'VOL(?P<volume>-\d\d|MT)')

ZON_PATTERN = re.compile('\#Z(?P<zone>\d{1,2}),'
                     '(?P<power>ON|OFF),'
                     'SRC(?P<source>\d),'
                     'VOL(?P<volume>\d{1,2}|MUTE),'
                     'DND(?P<dnd>1|0),'
                     'LOCK(?P<keypadlock>1|0)')

ZOFF_PATTERN = re.compile('\#Z(?P<zone>\d{1,2}),'
                     '(?P<power>ON|OFF)')

'''
Z02STR+"TUNER"
'''
SOURCE_PATTERN = re.compile('Z0(?P<zone>\d)'
                     'STR\+\"(?P<name>.*)\"')


EOL = b'\r'
#TIMEOUT_OP       = 0.2   # Number of seconds before serial operation timeout
TIMEOUT_OP       = 0.4   # Number of seconds before serial operation timeout
TIMEOUT_RESPONSE = 2.5   # Number of seconds before command response timeout
VOLUME_DEFAULT  = 0.40    # Value used when zone is muted or otherwise unable to get volume integer

class ZoneStatus(object):
    def __init__(self
                 ,zone: int
                 ,power: str
                 ,source: int
                 ,volume: float  # -78 -> 0
                 ):
        _LOGGER.warning("ZoneStatus init for Zone" + str(zone))
        self.zone = zone
        if 'ON' in power:
           self.power = bool(1)
        else:
           self.power = bool(0)
        self.source = str(source)
        self.sourcename = ''
#        self.treble = treble
#        self.bass = bass
        _LOGGER.warning("volume == None is " + str(volume == None))
        _LOGGER.warning("volume is " + str(volume))
        if volume == None:
            _LOGGER.warning("setting vol/mute to defaults")
            self.mute = bool(1)
            self.volume = VOLUME_DEFAULT
        else:
            if volume == 0:
                _LOGGER.warning("setting mute to 1 and volume to 0")
                self.mute = bool(1)
                self.volume = 0
            else:
                _LOGGER.warning("setting mute to 0 and volume to " + str(volume))
                self.mute = bool(0)
                self.volume = volume
        self.treble = 0 
        self.bass = 0
        _LOGGER.warning("leaving ZoneStatus Init for zone " + str(zone))


    @classmethod
    def from_string(cls, string: bytes):
        _LOGGER.warning("Zonestatus from_string fired")
        if not string:
            return None
        ret = match_response(string)
        _LOGGER.warning("Leaving ZoneStatus.From_string")
        return ret

def volumevaluetopercent(volumevalue: int):
    if volumevalue == 0:
        vol = 0
    else:
        vol = round(int(volumevalue) / 78,2)
        vol = round(1-vol,2)
        vol = vol * 100
    
    _LOGGER.warning("Converted Nuvo volume " + str(volumevalue) + " to percent value " + str(vol))
    return vol

class Nuvo(object):
    """
    Nuvo amplifier interface
    """

    def zone_status(self, zone: int):
        """
        Get the structure representing the status of the zone
        :param zone: zone 1.12
        :return: status of the zone or None
        """
        raise NotImplemented()

    def set_power(self, zone: int, power: bool):
        """
        Turn zone on or off
        :param zone: zone 1.12        
        :param power: True to turn on, False to turn off
        """
        raise NotImplemented()

    def set_mute(self, zone: int, mute: bool):
        """
        Mute zone on or off
        :param zone: zone 1.12        
        :param mute: True to mute, False to unmute
        """
        raise NotImplemented()

    def set_volume(self, zone: int, volume: float):
        """
        Set volume for zone
        :param zone: zone 1.12        
        :param volume: float from -78 to 0 inclusive
        """
        raise NotImplemented()

    def set_treble(self, zone: int, treble: float):
        """
        Set treble for zone
        :param zone: zone 1.12        
        :param treble: float from -12 to 12 inclusive
        """
        raise NotImplemented()

    def set_bass(self, zone: int, bass: int):
        """
        Set bass for zone
        :param zone: zone 1.12        
        :param bass: float from -12 to 12 inclusive 
        """
        raise NotImplemented()

    def set_source(self, zone: int, source: int):
        """
        Set source for zone
        :param zone: zone 1.6        
        :param source: integer from 1 to 6 inclusive
        """
        raise NotImplemented()

    def restore_zone(self, status: ZoneStatus):
        """
        Restores zone to it's previous state
        :param status: zone state to restore
        """
        raise NotImplemented()


# Helpers

def _is_int(s):
    try: 
        int(s)
        return True
    except ValueError:
        return False

def match_response(string: bytes):
        _LOGGER.warning("match_response")

        match = _parse_response(string)

        _LOGGER.warning("match_response from string match is " + str(match))

        if not match:
            _LOGGER.warning("match_response no match, returning none")
            return None

        #try:
        _LOGGER.warning("match_response match[0] is " + match[0])
        if match[0] == "#ZON":
            rtn = ZoneStatus(match[1], match[2], match[3], volumevaluetopercent(match[4]))
            _LOGGER.warning("Back in match_response from Zonestatus")
            _LOGGER.warning("match_response from string rtn power is " + str(rtn.power))
            _LOGGER.warning("match_response from string rtn zone is " + str(rtn.zone))
            _LOGGER.warning("match_response from string rtn source is " + str(rtn.source))
            _LOGGER.warning("match_response from string rtn volume is " + str(rtn.volume))
        
        elif match[0] == "#ZOFF":
            rtn = ZoneStatus(match[1], match[2], None, None)
            _LOGGER.warning("match_response from string rtn ZOFF is " + str(rtn))            

        else:
            #rtn = ZoneStatus(*[str(m) for m in match.groups()])
            _LOGGER.warning("other match")
            rtn = ZoneStatus(match[1], match[2],None, None)
            _LOGGER.warning("match_response from string rtn is " + str(rtn))
        #except:
        #    _LOGGER.warning("Error in try zonestatus (in from_string)")
        #    rtn = None
        _LOGGER.warning("Leaving Match_response")
        return rtn

def volumepercenttovalue(volumepercent):
    voldB = round((volumepercent) * 78, 0)
    if voldB < 10:
        _LOGGER.warning("converted vol percent of " + str(volumepercent) + " to volume 0" + str(voldB))
        return "0" + str(voldB)
    else:
        _LOGGER.warning("converted vol percent of " + str(volumepercent) + " to volume " + str(voldB))
        return str(voldB)

def _parse_response(string: str):
    _LOGGER.warning(" In parse_response witn " + string)
    """
    :param request: request that is sent to the nuvo
    :return: regular expression return match(s) 
    """

    match = re.search(CONCERTO_PATTERN, string)
    if match:
        _LOGGER.warning('CONCERTO_PATTERN - Match')
        return match

    match = re.search(ZON_PATTERN, string)
    if match:
        returnlist = ["#ZON"]
        for m in match.groups():
            returnlist.append(str(m))
        _LOGGER.warning('Leaving Parse_response with ZON_PATTERN - Match' + str(returnlist))
        return returnlist

    match = re.search(ZOFF_PATTERN, string)
    if match:
        returnlist = ["#ZOFF"]
        for m in match.groups():
            returnlist.append(str(m))
        _LOGGER.warning('Leaving Parse_response with ZOFF_PATTERN - Match' + str(returnlist))
        return returnlist

    match = re.search(SOURCE_PATTERN, string)
    if match:
        _LOGGER.debug('Leaving Parse_response with SOURCE_PATTERN - Match')
        return match

    if (string == '#Busy'):
        _LOGGER.debug('BUSY RESPONSE - TRY AGAIN')
        return None

    if not match:
        _LOGGER.debug('NO MATCH - %s' , string)
    _LOGGER.warning("Leaving Parse_response with No Match")
    return None

def _format_zone_status_request(zone: int) -> str:
    _LOGGER.warning("_format_zone_status_request - Zone for status request is " + str(zone))
    return 'Z{}STATUS?'.format(zone)

def _format_set_power(zone: int, power: bool) -> str:
    zone = int(zone)
    if (power):
       return 'Z{}ON'.format(zone) 
    else:
       return 'Z{}OFF'.format(zone)

def _format_set_mute(zone: int, mute: bool) -> str:
    if (mute):
       return 'Z{}MTON'.format(int(zone))
    else:
       return 'Z{}MTOFF'.format(int(zone))

def _format_set_volume(zone: int, volume: float) -> str:
    # If muted, status has no info on volume level
    volume = volumepercenttovalue(volume)

    #if _is_int(volume):
    #   # Negative sign in volume parm produces erronous result
    #   #volume = abs(volume)
    #   volume = round(volume,2)
    #else:
    #   # set to default value
    #   volume = abs(VOLUME_DEFAULT) 

    return 'Z{}VOL{}'.format(int(zone),volume)

def _format_set_treble(zone: int, treble: int) -> bytes:
    treble = int(max(12, min(treble, -12)))
    return 'Z{}TREB{}'.format(int(zone),treble)

def _format_set_bass(zone: int, bass: int) -> bytes:
    bass = int(max(12, min(bass, -12)))
    return 'Z{}BASS{:}'.format(int(zone),bass)

def _format_set_source(zone: int, source: int) -> str:
    source = int(max(1, min(int(source), 6)))
    return 'Z{}SRC{}'.format(int(zone),source)

def get_nuvo(port_url):
    """
    Return synchronous version of Nuvo interface
    :param port_url: serial port, i.e. '/dev/ttyUSB0,/dev/ttyS0'
    :return: synchronous implementation of Nuvo interface
    """

    lock = RLock()

    def synchronized(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with lock:
                return func(*args, **kwargs)
        return wrapper

    class NuvoSync(Nuvo):
        def __init__(self, port_url):
            _LOGGER.debug('Attempting connection - "%s"', port_url)
            self._port = serial.serial_for_url(port_url, do_not_open=True)
            self._port.baudrate = 57600
            self._port.stopbits = serial.STOPBITS_ONE
            self._port.bytesize = serial.EIGHTBITS
            self._port.parity = serial.PARITY_NONE
            self._port.timeout = TIMEOUT_OP
            self._port.write_timeout = TIMEOUT_OP
            self._port.open()
            self._nuvo = Nuvo


        def _send_request(self, request):
            _LOGGER.warning("send_request")
            """
            :param request: request that is sent to the nuvo
            :return: bool if transmit success
            """
            #format and send output command
            lineout = "*" + request + "\r"
            _LOGGER.warning('Sending "%s"', lineout)
            #Below line is not displayed properly in logger
            #_LOGGER.info('Sending "%s"', lineout)
            self._port.write(lineout.encode())
            self._port.flush() # it is buffering
            _LOGGER.warning("Leaving send_request")
            return True


        def _listen_maybewait(self, wait_for_response: bool, first_execution: bool):
            _LOGGER.warning("Listen_maybewait")

            no_data = False
            receive_buffer = b''
            message = b''
            start_time = time.time()
            timeout = TIMEOUT_RESPONSE 

            # listen for response
            while (no_data == False):
               # Exit if timeout
               if( (time.time() - start_time) > timeout ):
                  _LOGGER.warning('Leaving Listen_maybewait - Expected response from command but no response before timeout')
                  return None
               # fill buffer until we get term seperator 
               data = self._port.read(1)

               if data:
                  receive_buffer += data

                  if EOL in receive_buffer:
                     message, sep, receive_buffer = receive_buffer.partition(EOL)
                     _LOGGER.warning('Listen_maybe_wait Received this: %s', message)
                     stringmessage = message.decode('ascii')
                     stringmessage = stringmessage.strip()
                     rtn = match_response(stringmessage)
                     _LOGGER.warning("Leaving listen_maybewait - return from match_response is " + str(rtn))
                     #rtn = _parse_response(stringmessage)
                     return(rtn)
                  else:
                     _LOGGER.debug('Listen_maybewait - Expecting response from command sent - Data received but no EOL yet :(')
               else:
                  _LOGGER.warning('Listen_maybewaitExpecting response from command sent - No Data received')
                  if ( wait_for_response == False ): 
                     no_data = True
                     if first_execution:
                         _LOGGER.warning("Leaving Listen_maybewait because first execution. return none")
                         return None
                  continue

            _LOGGER.warning("Listen_maybewait - Should never get here")
            return None

        def _process_request(self, request: str, first_execution:bool):
            _LOGGER.warning("process_request")
            """
            :param request: request that is sent to the nuvo
            :return: ascii string returned by nuvo
            """
            # Process any messages that have already been received 
            self._listen_maybewait(False, first_execution)
            _LOGGER.warning("Back in Process Request from 1st listen_maybewait")
            # Send command to device
            self._send_request(request)
            _LOGGER.warning("Back in Process_request from send_request")
            # Process expected response
            rtn =  self._listen_maybewait(True, False)
            _LOGGER.warning("Back in Process Request from 2nd listen_maybewait")
            _LOGGER.warning("Leaving Process_request")
            return rtn

        @synchronized
        def zone_status(self, zone: int):
            _LOGGER.warning("zone_status for " + str(zone))
            # Send command multiple times, since we need result back, and rarely response can be wrong type 
            for count in range(1,5):
               try:
                  #_LOGGER.warning("Calling Zone status request from zone_status for zone" + str(zone) + " and count is " + str(count))
                  #rtn = ZoneStatus.from_string(self._process_request(_format_zone_status_request(zone), False))
                  rtn = self._process_request(_format_zone_status_request(zone), False)
                  _LOGGER.warning("Back in zone_status and count is " + str(count))
                  if rtn == None:
                     _LOGGER.warning('Zone Status Request - Response Invalid - Retry Count: %d' , count)
                     raise ValueError('Zone Status Request - Response Invalid')
                  else:
                     _LOGGER.warning("Got the response we were looking for")
                     return rtn
               except:
                  rtn = None
               #Wait 1 sec between retry attempt(s)
               time.sleep(1)
               continue  # end of for loop // retry
            _LOGGER.warning("Leaving zone_status")
            return rtn

        @synchronized
        def set_power(self, zone: int, power: bool):
            _LOGGER.warning("Set_power to " + str(power) + " in zone "+ str(zone))
            rtn = self._process_request(_format_set_power(zone, power), False)
            _LOGGER.warning("back in set_power from Process_request and now leaving set_power with " + str(rtn))
            return rtn

        @synchronized
        def set_mute(self, zone: int, mute: bool):
            _LOGGER.warning("set_mute to " + str(mute) + " in zone "+ str(zone))
            rtn = self._process_request(_format_set_mute(zone, mute), False)
            _LOGGER.warning("back in set_mute from process_request and now leaving set_mute with " + str(rtn))
            return rtn

        @synchronized
        def set_volume(self, zone: int, volume: float):
            _LOGGER.warning("set_volume to " + str(volume) + " in zone "+ str(zone))
            _LOGGER.warning("abs(volume is " + str(abs(volume)))
            _LOGGER.warning("abs(volume)/100 is " + str(abs(volume)/100))
            rtn = self._process_request(_format_set_volume(zone, (abs(volume)/100)), False)
            _LOGGER.warning("back in set_volume from process_request and now leaving set_volume with " + str(rtn))
            return rtn

        @synchronized
        def set_treble(self, zone: int, treble: float):
            _LOGGER.warning("set_treble in zone "+ str(zone))
            rtn = self._process_request(_format_set_treble(zone, treble), False)
            _LOGGER.warning("back in set_treble from process_request and now leaving set_treble with " + str(rtn))
            return rtn

        @synchronized
        def set_bass(self, zone: int, bass: float):
            _LOGGER.warning("set_bass in zone "+ str(zone))
            rtn = self._process_request(_format_set_bass(zone, bass), False)
            _LOGGER.warning("back in set_bass from process_request and now leaving set_base with " + str(rtn))
            return rtn

        @synchronized
        def set_source(self, zone: int, source: int):
            _LOGGER.warning("set_source to " + str(source) + " in zone "+ str(zone))
            rtn = self._process_request(_format_set_source(zone, source), False)
            _LOGGER.warning("back in set_source from process_request and now leaving set_source with " + str(rtn))
            return rtn

        @synchronized
        def restore_zone(self, status: ZoneStatus):
            _LOGGER.warning("restore_zone")
            self.set_power(status.zone, status.power)
            self.set_mute(status.zone, status.mute)
            self.set_volume(status.zone, status.volume)
            self.set_source(status.zone, status.source)
            _LOGGER.warning("Leaving restore_zone")

#            self.set_treble(status.zone, status.treble)
#            self.set_bass(status.zone, status.bass)

    
    _LOGGER.warning("about to leave NuvoSync")
    return NuvoSync(port_url)


#************************************************************************************************************************************************************************************

"""Support for interfacing with Nuvo Multi-Zone Amplifier via serial/RS-232."""

import logging

import voluptuous as vol

from homeassistant.components.media_player import MediaPlayerEntity, PLATFORM_SCHEMA
from homeassistant.components.media_player.const import (
    DOMAIN,
    SUPPORT_SELECT_SOURCE,
    SUPPORT_TURN_OFF,
    SUPPORT_TURN_ON,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_SET,
    SUPPORT_VOLUME_STEP,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_NAME,
    CONF_PORT,
    STATE_OFF,
    STATE_ON,
)
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

SUPPORT_NUVO = SUPPORT_VOLUME_MUTE | SUPPORT_VOLUME_SET | \
                    SUPPORT_VOLUME_STEP | SUPPORT_TURN_ON | \
                    SUPPORT_TURN_OFF | SUPPORT_SELECT_SOURCE

ZONE_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): cv.string,
})

SOURCE_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): cv.string,
})

CONF_ZONES = 'zones'
CONF_SOURCES = 'sources'
CONF_MODEL = 'model'

DATA_NUVO = 'nuvo'

SERVICE_SNAPSHOT = 'snapshot'
SERVICE_RESTORE = 'restore'

# Valid zone ids: 1-12
ZONE_IDS = vol.All(vol.Coerce(int), vol.Any(
    vol.Range(min=1, max=20)))

# Valid source ids: 1-6
SOURCE_IDS = vol.All(vol.Coerce(int), vol.Range(min=1, max=6))

MEDIA_PLAYER_SCHEMA = vol.Schema({ATTR_ENTITY_ID: cv.comp_entity_ids})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_PORT): cv.string,
    vol.Required(CONF_ZONES): vol.Schema({ZONE_IDS: ZONE_SCHEMA}),
    vol.Required(CONF_SOURCES): vol.Schema({SOURCE_IDS: SOURCE_SCHEMA}),
    vol.Optional(CONF_MODEL): cv.string,
})

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Nuvo multi zone amplifier platform."""
    port = config.get(CONF_PORT)

    from serial import SerialException
#    from pynuvo import get_nuvo
    try:
        nuvo = get_nuvo(port)
    except SerialException:
        _LOGGER.error("Error connecting to Nuvo controller")
        return

    sources = {source_id: extra[CONF_NAME] for source_id, extra
               in config[CONF_SOURCES].items()}

    _LOGGER.warning("Number of sources is " + str(len(sources)))
    for i in range(1, (len(sources)+1)):
        _LOGGER.warning("trying to get source " + str(i))
        _LOGGER.warning("Sources list at " + str(i) + " is " + str(sources[i]))

    hass.data[DATA_NUVO] = []
    for zone_id, extra in config[CONF_ZONES].items():
        _LOGGER.info("Adding zone %d - %s", zone_id, extra[CONF_NAME])
        hass.data[DATA_NUVO].append(NuvoZone(
            nuvo, sources, zone_id, extra[CONF_NAME]))

    add_entities(hass.data[DATA_NUVO], True)

    def service_handle(service):
        _LOGGER.warning("service_handle")
        """Handle for services."""
        entity_ids = service.data.get(ATTR_ENTITY_ID)

        if entity_ids:
            devices = [device for device in hass.data[DATA_NUVO]
                       if device.entity_id in entity_ids]
        else:
            devices = hass.data[DATA_NUVO]

        for device in devices:
            if service.service == SERVICE_SNAPSHOT:
                device.snapshot()
            elif service.service == SERVICE_RESTORE:
                device.restore()

    hass.services.register(
        DOMAIN, SERVICE_SNAPSHOT, service_handle, schema=MEDIA_PLAYER_SCHEMA)

    hass.services.register(
        DOMAIN, SERVICE_RESTORE, service_handle, schema=MEDIA_PLAYER_SCHEMA)


class NuvoZone(MediaPlayerEntity):
    """Representation of a Nuvo amplifier zone."""

    def __init__(self, nuvo, sources, zone_id, zone_name):
        """Initialize new zone."""
        _LOGGER.warning("Nuvozone init for zone " + str(zone_id))
        self._nuvo = nuvo
        # dict source_id -> source name
        self._source_id_name = sources
        # dict source name -> source_id
        self._source_name_id = {v: k for k, v in sources.items()}
        # ordered list of all source names
        self._source_names = sorted(self._source_name_id.keys(),
                                    key=lambda v: self._source_name_id[v])
        self._zone_id = zone_id
        self._name = zone_name

        self._snapshot = None
        self._state = STATE_OFF
        self._volume = None
        self._source = None
        self._mute = None
        self._last_update = datetime.datetime.now()
        #_LOGGER.warning("sending status request from init for zone " + str(zone_id))
        #rtn = ZoneStatus.from_string(self._nuvo._process_request(_format_zone_status_request(zone_id), False))
        #if not rtn == None:
        #    _LOGGER.warning("done in init, power is " + str(rtn.power))
        #    _LOGGER.warning("done in init, zone is " + str(rtn.zone))
        #    _LOGGER.warning("done in init, source is " + str(rtn.source))
        #    _LOGGER.warning("done in init, volume is " + str(rtn.volume))

    def update(self):
        """Retrieve latest state."""
        _LOGGER.warning("Nuvozone update for zone " + str(self._zone_id))
        _LOGGER.warning("Calling zonestatus from update for " + str(self._zone_id))
        state = self._nuvo.zone_status(self._zone_id)
        _LOGGER.warning("NuvoZone Update back from Zone_status")
        if not state:
            _LOGGER.warning("not state is true, exiting update")
            return False
        _LOGGER.warning("power is " + str(state.power) + " volume is " + str(state.volume) + " mute is " + str(state.mute))
        _LOGGER.warning("source is " + str(state.source))
        self._state = STATE_ON if state.power else STATE_OFF
        self._volume = state.volume
        self._mute = state.mute
        
        if (not (state.source == "None")):
            self._source = str(self._source_id_name[int(state.source)])
            _LOGGER.warning("update - setting source name to " + str(self._source_id_name[int(state.source)]))
        else:
            self._source = None
            _LOGGER.warning("update - Unable to find source name, setting to none")
            
        _LOGGER.warning("done in update")
        return True

    @classmethod
    def update_info(self, update_object, destination_object):
        """ updates the HA settings with what was recieved"""
        if not update_object.power == None:
            _LOGGER.warning("Setting Power to " + str(update_object.power))
            self._state = update_object.power
        if not update_object.volume == None:
            _LOGGER.warning("Setting volume to " + str(update_object.volume))
            self._volume = update_object.volume
        if not update_object.source == None:
            _LOGGER.warning("Source ID is " + str(update_object.source))
            idx = update_object.source
            if idx in destination_object._source_id_name:
                self._source = destination_object._source_id_name[idx]
                _LOGGER.warning("update_info - found sourcename " + str(destination_object._source_id_name[idx]))
            else:
                _LOGGER.warning("update_info - unable to find source Name")
        else:
            self._source = None
            _LOGGER.warning("source name is  " + self._nuvo._source_id-name[update_object.source])
            self._source = self._nuvo._source_id-name[update_object.source]
        if not update_object.mute == None:
            _LOGGER.warning("Setting mute to " + str(update_object.mute))
            self._mute = update_object.mute

    @property
    def name(self):
        """Return the name of the zone."""
        return self._name

    @property
    def state(self):
        """Return the state of the zone."""
        return self._state

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        if self._volume is None:
            return None
        return (( int(self._volume) + 78) / 78)

    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        return self._mute

    @property
    def supported_features(self):
        """Return flag of media commands that are supported."""
        return SUPPORT_NUVO

    @property
    def media_title(self):
        """Return the current source as medial title."""
        return self._source

    @property
    def source(self):
        """Return the current input source of the device."""
        return self._source

    @property
    def source_list(self):
        """List of available input sources."""
        return self._source_names

    def snapshot(self):
        """Save zone's current state."""
        _LOGGER.warning("Calling Zone_Status from Snapshot for zone " + str(self._zone_id))
        self._snapshot = self._nuvo.zone_status(self._zone_id)
        _LOGGER.warning("Back in snapshot")

    def restore(self):
        """Restore saved state."""
        if self._snapshot:
            self._nuvo.restore_zone(self._snapshot)
            self.schedule_update_ha_state(True)

    def select_source(self, source):
        """Set input source."""
        if source not in self._source_name_id:
            return
        idx = self._source_name_id[source]
        rtn = self._nuvo.set_source(self._zone_id, idx)
        self.update_info(rtn, self)

    def turn_on(self):
        """Turn the media player on."""
        _LOGGER.warning("attempting to turn on zone " + str(self._zone_id))
        rtn = self._nuvo.set_power(self._zone_id, True)
        _LOGGER.warning("back in turn on, got rtn = " + str(rtn))
        self.update_info(rtn, self)

    def turn_off(self):
        """Turn the media player off."""
        _LOGGER.warning("attempting to turn off zone " + str(self._zone_id))
        rtn = self._nuvo.set_power(self._zone_id, False)
        _LOGGER.warning("returned to turn off, got rtn = " + str(rtn))
        self.update_info(rtn, self)

    def mute_volume(self, mute):
        """Mute (true) or unmute (false) media player."""
        rtn = self._nuvo.set_mute(self._zone_id, mute)
        self.update_info(rtn, self)

    def set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        _LOGGER.warning("attempting to set Zone " + str(self._zone_id) + " volume to " + str(volume))
        rtn = self._nuvo.set_volume(self._zone_id, int( (volume * 78) - 78) )
        self.update_info(rtn, self)

    def volume_up(self):
        """Volume up the media player."""
        if self._volume is None:
            return
        rtn = self._nuvo.set_volume(self._zone_id, min(self._volume + 1, 0))
        self.update_info(rtn, self)

    def volume_down(self):
        """Volume down media player."""
        if self._volume is None:
            return
        rtn = self._nuvo.set_volume(self._zone_id, max(self._volume - 1, -78))
        self.update_info(rtn, self)

