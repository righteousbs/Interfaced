import sys, os, jumpy, urllib2, logging, re
import urllib, time, shelve, json
from xml.dom import minidom
from operator import itemgetter
from hashlib import sha1

# BEGIN USER INPUTS
TEMP_FILE = 'temp'
LOG_FILE = 'InterfacedDebug.log'

PLEX_SERVER_HOST = 'localhost:32400'                  	# your host:port

HAVE_TRAKT = True                               		# True or False
TRAKT_USERNAME = 'INSERT Your Username Here'            # your username
TRAKT_PASSWORD = 'INSERT Your Password Here'            # your password
TRAKT_API = 'INSERT Your API Key Here' 			        # your api key

HAVE_PUSHOVER = True                               		# True or False
PUSHOVER_SCRIPTAPI = 'INSERT Your API Key Here'         # your script api key
PUSHOVER_USERKEY = 'INSERT Your USER API Key Here'   	# your user api key
# END USER INPUTS

logging.basicConfig(filename=LOG_FILE,level=logging.DEBUG)

# Interface with Pushover
class Pushover:

    def _userKey(self):
        return PUSHOVER_USERKEY

    def _api(self):
        return PUSHOVER_SCRIPTAPI
    
    def _notify(self, api, userKey, data = {}):
        
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
            self._notify(None, None, data) 


# Interface with Plex
class Plex:

    def _hostName(self):
        return PLEX_SERVER_HOST
    
    def _notify(self, method, hostName):

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
    
    def _request(self, method, hostName):

        # if the hostname isn't given then use the config hostname
        if not hostName:
            hostName= self._hostName()

        try:
            logging.debug("plex_requester: Calling method http://%s" % hostName + method)
            xml = minidom.parse(urllib2.urlopen("http://%s" % hostName + method))
        except Exception, e:
            logging.warning(u"Error reading from library: "+e)
            return None
        return xml

    def SnatchItems(self,method):
    
        plex_xml = self._request(method,None)
        directories_xml = plex_xml.getElementsByTagName('Directory')
        if directories_xml != []:
            # pull directories until we drill down to the media files
            plexItems = self.SnatchDirectoryItems(plex_xml,method)
            methodType = 'directory'
            
        else:
            # pull media files
            plexItems, methodType = self.SnatchMediaItems(plex_xml)
        
        return plexItems, methodType

    def SnatchDirectoryItems(self,plex_xml,method):
    
        dirItems = []
        directories_xml = plex_xml.getElementsByTagName('Directory')
        for directory_xml in directories_xml:
            filterTitle = directory_xml.getAttribute('title')
            filterKey   = directory_xml.getAttribute('key')
            if filterKey.find('library') != -1:
                nextMethod = filterKey # if the key contains its own library call, then use it over the appended version
            else:
                nextMethod = method + '/' + filterKey
            item = {'title': filterTitle,
                    'nextMethod': nextMethod}
            dirItems.append(item)
            
        return dirItems
        
    def SnatchMediaItems(self,plex_xml,reportFlag='all'):
                
        mediaContainer_xml = plex_xml.getElementsByTagName('MediaContainer')
        methodType = mediaContainer_xml[0].getAttribute('viewGroup')
        
        if methodType == 'movie' or methodType == 'episode':
            media_xml = plex_xml.getElementsByTagName('Video')
            
        elif methodType == 'photo':
            media_xml = plex_xml.getElementsByTagName('Photo')
            
        elif methodType == 'track':
            media_xml = plex_xml.getElementsByTagName('Track')
            
        mediaItems = []
        parts_xml = plex_xml.getElementsByTagName('Part')
        for index in range(0,len(media_xml)):
            ratingKey = str(media_xml[index].getAttribute('ratingKey')) # unique database identifier
            fullFileName = str(parts_xml[index].getAttribute('file'))
            
            if methodType == 'movie':
                (filePath, displayName) = os.path.split(fullFileName)

                viewCount = media_xml[index].getAttribute('viewCount')
                if (reportFlag == 'unwatched') and (viewCount != ''): # viewCount != 0
                    reportItem = False
                else:
                    reportItem = True
                    
                collectionTitle = media_xml[index].getAttribute('title') # movie name
                
            elif methodType == 'episode':
                episodeTitle = str(media_xml[index].getAttribute('title'))
                episodeNumber = str(media_xml[index].getAttribute('index'))
                seasonNumber = str(mediaContainer_xml[0].getAttribute('parentIndex'))
                displayName = 'S%sE%s - %s' %(seasonNumber.zfill(2), episodeNumber.zfill(2), episodeTitle)

                viewCount = media_xml[index].getAttribute('viewCount')
                if (reportFlag == 'unwatched') and (viewCount != ''): # viewCount != 0
                    reportItem = False
                else:
                    reportItem = True
                
                collectionTitle = media_xml[index].getAttribute('grandparentTitle') # show name
                
            elif methodType == 'photo':
                (filePath, displayName) = os.path.split(fullFileName)
                reportItem = True
                
                collectionTitle = media_xml[index].getAttribute('parentTitle') # album name
                
            elif methodType == 'track':
                (filePath, displayName) = os.path.split(fullFileName)
                reportItem = True
            
            if reportItem is True:
                item = {'ratingKey': ratingKey,
                        'fullFileName': fullFileName,
                        'displayName': displayName,
                        'collectionTitle': collectionTitle}
                mediaItems.append(item)
        
        return mediaItems, methodType
            
    def CustomRecentlyAddedVideos(self):
        
        videos = []
        sections_xml = self._request('/library/sections',None)
        if sections_xml is None:
            return videos
        sectionDirectories_xml = sections_xml.getElementsByTagName('Directory')

        for sectionDirectory in sectionDirectories_xml:
            sectionType = sectionDirectory.getAttribute('type')
            if sectionType == "show" or sectionType == "movie":
                
                videoSectionKey = sectionDirectory.getAttribute('key')
                plexMedia_xml = self._request('/library/sections/%s/recentlyAdded' % videoSectionKey,None)
                
                plexItems, methodType = self.SnatchMediaItems(plexMedia_xml,'unwatched')
                for item in plexItems:
                    videos.append(item)
        
        return videos

    def CustomUnwatchedVideos(self):
        
        videos = []
        sections_xml = self._request('/library/sections',None)
        if sections_xml is None:
            return videos
        sectionDirectories_xml = sections_xml.getElementsByTagName('Directory')

        for sectionDirectory in sectionDirectories_xml:
            sectionType = sectionDirectory.getAttribute('type')
            if sectionType == "show" or sectionType == "movie":
                
                videoSectionKey = sectionDirectory.getAttribute('key')
                unWatched_xml = self._request('/library/sections/%s/unwatched' % videoSectionKey, None)

                if sectionType == "movie":
                    plexItems, methodType = self.SnatchMediaItems(unWatched_xml,'unwatched')
                    for item in plexItems:
                        videos.append(item)
                    
                elif sectionType == "show":
                    showDirectories_xml = unWatched_xml.getElementsByTagName('Directory')
                    for showDirectory in showDirectories_xml:
                        ratingKey = str(showDirectory.getAttribute('ratingKey')) # unique database identifier
                        title = showDirectory.getAttribute('title')
                        showUnWatched_xml = self._request('/library/metadata/%s/allLeaves?unwatched=1' % ratingKey, None)
                        
                        plexItems, methodType = self.SnatchMediaItems(showUnWatched_xml,'unwatched')
                        for item in plexItems:
                            videos.append(item)
                        
        return videos
                                
    def MetaData(self, ratingKey):
        
        method = '/library/metadata/%s' % ratingKey
        plexMediaContainer_xml = self._request(method, None)
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
        self._notify(method,None)

    def UnScrobble(self, ratingKey):
        method = ':/unscrobble?identifier=com.plexapp.plugins.library&key=%s' % ratingKey
        self._notify(method,None)
        
        
# Interface with Trakt
class Trakt:

    def _username(self):
        return TRAKT_USERNAME

    def _password(self):
        return TRAKT_PASSWORD

    def _api(self):
        return TRAKT_API
        
    def _notify(self, method, api, username, password, data = {}):

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
            self._notify(method, None, None, None, data) 


# Interface with PS3/Universal Media Server
if (len(sys.argv) == 1) or (sys.argv[1] == 'DisplayRequest'):
    if len(sys.argv) == 1:
        # intialization

        # display my custom directories
        pms.addItem(PMS_FOLDER, 'Custom Filters', [sys.argv[0], 'DisplayCustomFilters'])
        
        # display section directories
        method = '/library/sections'
    else:
        # callback: display method request all the way down to the media files
        method = sys.argv[2]
    
    # pull method request
    plexItems, methodType = Plex().SnatchItems(method)
    
    # display method request
    if methodType == 'directory':
        for item in plexItems:
            pms.addItem(PMS_FOLDER, item['title'], [sys.argv[0], 'DisplayRequest', item['nextMethod']])
        
    elif methodType == 'movie' or methodType == 'episode':
        pms.addItem(PMS_FOLDER, '# -- Scrobble -- #', [sys.argv[0], 'DisplayScrobble', method])
        for item in plexItems:
            pms.addItem(PMS_VIDEO, item['displayName'], item['fullFileName'])
        
    elif methodType == 'photo':
        for item in plexItems:
            pms.addItem(PMS_IMAGE, item['displayName'], item['fullFileName'])
        
    elif methodType == 'audio':
        for item in plexItems:
            pms.addItem(PMS_AUDIO, item['displayName'], item['fullFileName'])


elif sys.argv[1] == 'DisplayScrobble':

    if len(sys.argv) == 2:
        # use temp file
        d = shelve.open(TEMP_FILE)
        plexItems = d['customFileInfo']
        d.close()
    elif len(sys.argv) == 3:
        # use method call argument
        method = sys.argv[2]
        plexItems, methodType = Plex().SnatchItems(method)
    
    for item in plexItems:
        pms.addAction('scrobble %s' % item['displayName'], [sys.argv[0], 'Scrobble', item['ratingKey']])
##        pms.addItem(PMS_FOLDER, item['displayName'], [sys.argv[0], 'Scrobble', item['ratingKey']])


elif sys.argv[1] == 'Scrobble':

    ratingKey = sys.argv[2]
    temp = '%s\\nhas been scrobbled' % ratingKey
    print temp
    
    plex = Plex()
    plex.Scrobble(ratingKey)

    if HAVE_TRAKT or HAVE_PUSHOVER:
        metaData = plex.MetaData(ratingKey)
    
    if HAVE_TRAKT:
        Trakt().Scrobble(metaData)
    
    if HAVE_PUSHOVER:
        Pushover().Scrobble(metaData)
    
    pms.ok('%s\\nhas been scrobbled' % ratingKey)


# custom folder callbacks       
elif sys.argv[1] == 'DisplayCustomFilters':
    pms.addItem(PMS_FOLDER, 'Unwatched Videos', [sys.argv[0], 'DisplayCustomVideoFolder', 'unwatched'])
    pms.addItem(PMS_FOLDER, 'Recently Added Videos', [sys.argv[0], 'DisplayCustomVideoFolder', 'recent'])


elif sys.argv[1] == 'DisplayCustomVideoFolder':
    source = sys.argv[2]
    if source == 'unwatched':
        videos = Plex().CustomUnwatchedVideos()
    elif source == 'recent':
        videos = Plex().CustomRecentlyAddedVideos()
    
    # store for later usage (DisplayCustomVideos)
    d = shelve.open(TEMP_FILE)
    d['allVideos'] = videos
    d.close()
    
    # pull unique video titles
    titleList = map(itemgetter('collectionTitle'), videos)
    titles = list(set(titleList))
    
    # sort
    titles.sort()
    
    # display
    for title in titles:
        pms.addItem(PMS_FOLDER, title, [sys.argv[0], 'DisplayCustomVideos', title])
    

elif sys.argv[1] == 'DisplayCustomVideos':
    title = sys.argv[2]

    d = shelve.open(TEMP_FILE)
    videos = d['allVideos']
    d.close()
    
    # pull all videos associated to the movie/show, specified by 'title'
    titleVideos = []
    titleList = map(itemgetter('collectionTitle'), videos)
    for i, x in enumerate(titleList):
        if x == title:
            titleVideos.append(videos[i])
    
    # sort respective videos by filename
    fileInfo=[]
    for item in titleVideos:
        fullFileName = item['fullFileName']
        ratingKey = item['ratingKey']
        (filePath, displayName) = os.path.split(fullFileName)
        fileInfo.append((fullFileName,displayName,ratingKey))
    fileInfo.sort()

    # remake dictionary
    customFileInfo = []
    for item in fileInfo:
        customFileInfo.append({'fullFileName': item[0], 'displayName': item[1], 'ratingKey': item[2]})
    
    # store for later usage (DisplayScrobble)
    d = shelve.open(TEMP_FILE)
    d['customFileInfo'] = customFileInfo
    d.close()
    
    # display videos
    pms.addItem(PMS_FOLDER, '# -- Scrobble -- #', [sys.argv[0], 'DisplayScrobble'])
    for item in customFileInfo:
        pms.addItem(PMS_VIDEO, item['displayName'], item['fullFileName'])

