import sys, os, jumpy, urllib2, logging, re
from xml.dom import minidom
import urllib, time
import shelve
from operator import itemgetter

import json
from hashlib import sha1

# BEGIN USER INPUTS
HAVE_TRAKT    = True                                        # True or False
HAVE_PUSHOVER = True                                        # True or False
PLEX_SERVER_HOST   = 'localhost:32400'                      # your host:port
TRAKT_USERNAME     = 'INSERT Your Username Here'            # your username
TRAKT_PASSWORD     = 'INSERT Your Password Here'            # your password
TRAKT_API          = 'INSERT Your API Key Here'             # your api key
PUSHOVER_SCRIPTAPI = 'INSERT Your API Key Here'             # your script api key
PUSHOVER_USERKEY   = 'INSERT Your USER API Key Here'        # your user api key
# END USER INPUTS

# would like to know when a file is being served to ps3 so i can set watching status to trakt, and duration counter to plex
#		if i can do this i will need to reset the duration counters when video is fully scrobbled 

logging.basicConfig(filename='PlexTraktJumpyUMS.log',level=logging.DEBUG)

# Interface with Pushover
class Pushover:

    def _userKey(self):
        return PUSHOVER_USERKEY

    def _api(self):
        return PUSHOVER_SCRIPTAPI
    
    def _notifyPushover(self, api, userKey, data = {}):
        
        # if the API isn't given then use the config API
        if not api:
            api = self._api()

        # if the username isn't given then use the config username
        if not userKey:
            userKey= self._userKey()
        
        # build up the URL and parameters
        data["token"] = api
        data["user"]  = userKey
        data["timestamp"] = int(time.time())
        encoded_data = urllib.urlencode(data);

        # send the request to pushover
        try:
            logging.debug("pushover_notifier: Calling method https://api.pushover.net/1/messages.json, with data" + encoded_data)

            req = urllib2.Request("https://api.pushover.net/1/messages.json", encoded_data)
            response = urllib2.urlopen(req)
            output = response.read()
            resp = json.loads(output)
            
            if resp['status'] != 1:
                raise Exception(resp['status'])

        except (IOError):
            logging.warning("pushover_notifier: Failed calling method")
            return False

        if (resp["status"] == 1):
            logging.debug("pushover_notifier: Succeeded calling method")
            return True

        logging.warning("pushover_notifier: Failed calling method")
        return False

    def Scrobble(self,metaData):
        
        if metaData['itemType'] == 'movie':
            # URL parameters
            data = {'title': 'Scrobbled Movie', 'message': metaData['title'] + ' ' + metaData['year']}
            
        elif metaData['itemType'] == 'episode':
            # URL parameters
            data = {'title': 'Scrobbled Tv Show', 'message': metaData['title'] + ' - S' + str(metaData['season']).zfill(2) + 'E' + str(metaData['episode']).zfill(2)}
        else:
             data = {}
        
        if data is not None:
            self._notifyPushover(None, None, data) 


# Interface with Plex
class Plex:

    def _hostName(self):
        return PLEX_SERVER_HOST
    
    def _notifyPlex(self, method, hostName):

        # if the hostname isn't given then use the config hostname
        if not hostName:
            hostName= self._hostName()
        
        # request the URL from plex and parse the result as json
        try:
            urllib2.urlopen("http://%s/" % hostName + method)
            logging.debug("plex_notifier: Succeeded calling method http://%s/"% hostName + method)
            return True
            
        except Exception, e:
            logging.warning(u"plex_notifier: Error writing to library: "+e)
            return False
    
    def _requestPlex(self, method, hostName):

        # if the hostname isn't given then use the config hostname
        if not hostName:
            hostName= self._hostName()

        try:
            logging.debug("plex_requester: Calling method http://%s/" % hostName + method)
            xml = minidom.parse(urllib2.urlopen("http://%s/" % hostName + method))
        except Exception, e:
            logging.warning(u"Error reading from library: "+e)
            return None
        return xml
    
    def RecentlyAddedVideos(self):
        
        videos = []
        sections_xml = self._requestPlex('library/sections',None)
        if sections_xml is None:
            return videos
        sectionDirectories_xml = sections_xml.getElementsByTagName('Directory')

        for sectionDirectory in sectionDirectories_xml:
            sectionType = sectionDirectory.getAttribute('type')
            if sectionType == "show" or sectionType == "movie":
                
                videoSectionKey = sectionDirectory.getAttribute('key')
                plexMedia_xml = self._requestPlex('library/sections/%s/recentlyAdded' % videoSectionKey,None)
                
                videos_xml = plexMedia_xml.getElementsByTagName('Video')
                parts_xml  = plexMedia_xml.getElementsByTagName('Part')
                for index in range(0,len(videos_xml)):
                    ratingKey    = str(videos_xml[index].getAttribute('ratingKey')) # unique database identifier
                    if sectionType == "show":
                        title    = videos_xml[index].getAttribute('grandparentTitle')
                    elif sectionType == "movie":
                        title    = videos_xml[index].getAttribute('title')
                    fullFileName = str(parts_xml[index].getAttribute('file'))
                    viewCount    = videos_xml[index].getAttribute('viewCount')
                    if viewCount == '': # viewCount == 0
                        item = {'ratingKey': ratingKey,
                                'fullFileName': fullFileName,
                                'sectionType': sectionType,
                                'title': title}
                        videos.append(item)
        return videos

    def UnWatchedVideos(self):
        
        videos = []
        sections_xml = self._requestPlex('library/sections',None)
        if sections_xml is None:
            return videos
        sectionDirectories_xml = sections_xml.getElementsByTagName('Directory')

        for sectionDirectory in sectionDirectories_xml:
            sectionType = sectionDirectory.getAttribute('type')
            if sectionType == "show" or sectionType == "movie":
                
                videoSectionKey = sectionDirectory.getAttribute('key')
                unWatched_xml = self._requestPlex('library/sections/%s/unwatched' % videoSectionKey, None)

                if sectionType == "movie":
                    videos_xml = unWatched_xml.getElementsByTagName('Video')
                    parts_xml  = unWatched_xml.getElementsByTagName('Part')
                    for index in range(0,len(videos_xml)):
                        ratingKey    = str(videos_xml[index].getAttribute('ratingKey')) # unique database identifier
                        title        = videos_xml[index].getAttribute('title')
                        fullFileName = str(parts_xml[index].getAttribute('file'))
                        viewCount    = videos_xml[index].getAttribute('viewCount')
                        if viewCount == '': # viewCount == 0
                            item = {'ratingKey': ratingKey,
                                    'fullFileName': fullFileName,
                                    'sectionType': sectionType,
                                    'title': title}
                            videos.append(item)
                    
                elif sectionType == "show":
                    showDirectories_xml = unWatched_xml.getElementsByTagName('Directory')
                    for showDirectory in showDirectories_xml:
                        ratingKey = str(showDirectory.getAttribute('ratingKey')) # unique database identifier
                        title = showDirectory.getAttribute('title')
                        showUnWatched_xml = self._requestPlex('library/metadata/%s/allLeaves?unwatched=1' % ratingKey, None)
                        
                        videos_xml = showUnWatched_xml.getElementsByTagName('Video')
                        parts_xml  = showUnWatched_xml.getElementsByTagName('Part')
                        for index in range(0,len(videos_xml)):
                            ratingKey    = str(videos_xml[index].getAttribute('ratingKey')) # unique database identifier
                            fullFileName = str(parts_xml[index].getAttribute('file'))
                            viewCount    = videos_xml[index].getAttribute('viewCount')
                            if viewCount == '': # viewCount == 0
                                item = {'ratingKey': ratingKey,
                                        'fullFileName': fullFileName,
                                        'sectionType': sectionType,
                                        'title': title}
                                videos.append(item)
        return videos
                    
    def MetaData(self, ratingKey):
        
        method = 'library/metadata/%s' % ratingKey
        plexMediaContainer_xml = self._requestPlex(method, None)
        videos_xml = plexMediaContainer_xml.getElementsByTagName('Video')
        index = 0
        video_xml = videos_xml[index]
        
        metaData = {}
        itemType = video_xml.getAttribute('type')
        if itemType == 'movie':
            MOVIE_REGEXP = 'com.plexapp.agents.imdb://(tt[-a-z0-9\.]+)'
            metaData['itemType'] = itemType
            metaData['imdb_id']  = re.search(MOVIE_REGEXP,video_xml.getAttribute('guid')).group(1)
            metaData['title']    = video_xml.getAttribute('title')
            metaData['year']     = int(video_xml.getAttribute('year'))
            viewCount = video_xml.getAttribute('viewCount')
            if viewCount == '': # viewCount == 0
                viewCount = 0
            metaData['plays']    = int(viewCount)
            
        elif itemType == 'episode':
            #TVSHOW_REGEXP = 'com.plexapp.agents.thetvdb://([-a-z0-9\.]+)/([-a-z0-9\.]+)/([-a-z0-9\.]+)'
            TVSHOW_REGEXP = 'com.plexapp.agents.thetvdb://([-a-z0-9\.]+)'
            metaData['itemType'] = itemType
            metaData['tvdb_id']  = re.search(TVSHOW_REGEXP,video_xml.getAttribute('guid')).group(1)
            metaData['title']    = video_xml.getAttribute('grandparentTitle')
            metaData['year']     = int(video_xml.getAttribute('year'))
            metaData['season']   = int(video_xml.getAttribute('parentIndex'))
            metaData['episode']  = int(video_xml.getAttribute('index'))
            
        return metaData
    
    def Scrobble(self, ratingKey):
        method = ':/scrobble?identifier=com.plexapp.plugins.library&key=%s' % ratingKey
        self._notifyPlex(method,None)

    def UnScrobble(self, ratingKey):
        method = ':/unscrobble?identifier=com.plexapp.plugins.library&key=%s' % ratingKey
        self._notifyPlex(method,None)

        
# Interface with Trakt
class Trakt:

    def _username(self):
        return TRAKT_USERNAME

    def _password(self):
        return TRAKT_PASSWORD

    def _api(self):
        return TRAKT_API
        
    def _notifyTrakt(self, method, api, username, password, data = {}):

        logging.debug("trakt_notifier: Call method " + method)

        # if the API isn't given then use the config API
        if not api:
            api = self._api()

        # if the username isn't given then use the config username
        if not username:
            username = self._username()
        
        # if the password isn't given then use the config password
        if not password:
            password = self._password()
        password = sha1(password).hexdigest()

        # replace the API string with what we found
        method = method.replace("%API%", api)

        data["username"] = username
        data["password"] = password

        # take the URL params and make a json object out of them
        encoded_data = json.dumps(data);

        # request the URL from trakt and parse the result as json
        try:
            logging.debug("trakt_notifier: Calling method http://api.trakt.tv/" + method + ", with data" + encoded_data)
            stream = urllib2.urlopen("http://api.trakt.tv/" + method, encoded_data)
            resp = stream.read()

            resp = json.loads(resp)
            
            if ("error" in resp):
                raise Exception(resp["error"])

        except (IOError):
            logging.warning("trakt_notifier: Failed calling method")
            return False

        if (resp["status"] == "success"):
            logging.debug("trakt_notifier: Succeeded calling method. Result: " + resp["message"])
            return True

        logging.warning("trakt_notifier: Failed calling method")
        return False
           
    def Scrobble(self,metaData):
        
        if metaData['itemType'] == 'movie':
            # URL parameters
            method = "movie/seen/%API%"
            data = {
                'movies': [ {
                    'imdb_id': metaData['imdb_id'],
                    'title':   metaData['title'],
                    'year':    metaData['year'],
                    'plays':   metaData['plays']+1,
                    } ]
                }
            
        elif metaData['itemType'] == 'episode':
            # URL parameters
            method = "show/episode/seen/%API%"
            data = {
                'tvdb_id': metaData['tvdb_id'],
                'title':   metaData['title'],
                'year':    metaData['year'],
                'episodes': [ {
                    'season':  metaData['season'],
                    'episode': metaData['episode']
                    } ]
                }
        else:
             data = {}
        
        if data is not None:
            self._notifyTrakt(method, None, None, None, data) 


# Interface with PS3/Universal Media Server
if len(sys.argv) == 1:
    pms.addItem(PMS_FOLDER, 'Unwatched', [sys.argv[0], 'display video titles', 'unwatched'])
    pms.addItem(PMS_FOLDER, 'Recently Added', [sys.argv[0], 'display video titles', 'recent'])
  
# callbacks:
elif sys.argv[1] == 'display video titles':
    source = sys.argv[2]
    plex = Plex()
    if source == 'unwatched':
        videos = plex.UnWatchedVideos()
    elif source == 'recent':
        videos = plex.RecentlyAddedVideos()
    
    titleList = map(itemgetter('title'), videos)
    titles = list(set(titleList))
    titles.sort()
    for title in titles:
        pms.addItem(PMS_FOLDER, title, [sys.argv[0], 'display videos', title, source])
    
    d = shelve.open('temp')
    d['videos'] = videos
    d.close()
    
elif sys.argv[1] == 'display videos':
    title = sys.argv[2]
    source = sys.argv[3]
    pms.addItem(PMS_FOLDER, '# -- Scrobble -- #', [sys.argv[0], 'display videos to scrobble', title, source])

    d = shelve.open('temp')
    videos = d['videos']
    d.close()
    
    titleVideos = []
    titleList = map(itemgetter('title'), videos)
    for i, x in enumerate(titleList):
        if x == title:
            titleVideos.append(videos[i])
    
    fullFileNames=[]
    for item in titleVideos:
        fullFileName = item['fullFileName']
        fullFileNames.append(fullFileName)

    fullFileNames.sort()
    for fullFileName in fullFileNames:
        (filePath, fileName) = os.path.split(fullFileName)
        (fileBaseName, fileExtension) = os.path.splitext(fileName)
        pms.addItem(PMS_VIDEO, fileName, fullFileName)

elif sys.argv[1] == 'display videos to scrobble':
    title = sys.argv[2]
    source = sys.argv[3]
    
    d = shelve.open('temp')
    videos = d['videos']
    d.close()
    
    titleVideos = []
    titleList = map(itemgetter('title'), videos)
    for i, x in enumerate(titleList):
        if x == title:
            titleVideos.append(videos[i])
    
    fileInfo=[]
    for item in titleVideos:
        fullFileName = item['fullFileName']
        ratingKey    = item['ratingKey']
        fileInfo.append((fullFileName,ratingKey))

    fileInfo.sort()
    for item in fileInfo:
        fullFileName = item[0]
        ratingKey    = item[1]
        (filePath, fileName) = os.path.split(fullFileName)
        (fileBaseName, fileExtension) = os.path.splitext(fileName)
        pms.addItem(PMS_FOLDER, fileName, [sys.argv[0], 'scrobble', ratingKey, source])
  
elif sys.argv[1] == 'scrobble':
    ratingKey = sys.argv[2]
    source = sys.argv[3]
    
    plex = Plex()
    plex.Scrobble(ratingKey)

    if HAVE_TRAKT or HAVE_PUSHOVER:
        metaData = plex.MetaData(ratingKey)
    
    if HAVE_TRAKT:
        trakt = Trakt()
        trakt.Scrobble(metaData)
    
    if HAVE_PUSHOVER:
        pushover = Pushover()
        pushover.Scrobble(metaData)

##    if source == 'unwatched':
##        videos = plex.UnWatchedVideos()
##        d = shelve.open('temp')
##        d['videos'] = videos
##        d.close()
##    else:
##    d = shelve.open('temp')
##    videos = d['videos']
##    updatedVideos = []
##    ratingKeyList = map(itemgetter('ratingKey'), videos)
##    for i, x in enumerate(ratingKeyList):
##        if x != ratingKey:
##            updatedVideos.append(videos[i])
##    d['videos'] = updatedVideos
##    d.close()
