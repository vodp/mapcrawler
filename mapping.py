#!/usr/bin/python
'''
    This utility has functions helping obtaining longtitude and latitude
    bounding box of a city and then download the corresponding satellite
    map from Google Maps service.
'''
import io
import math
import json
import urllib2
import os, sys
import argparse
import time
import logging
import random
import requests
from PIL import Image
from progressbar import ProgressBar, SimpleProgress

def latlon2px(z,lat,lon):

    x = 2**z*(lon+180)/360*256
    y = -(.5*math.log((1+math.sin(math.radians(lat)))/(1-math.sin(math.radians(lat))))/math.pi-1)*256*2**(z-1)
    return x,y

def latlon2xy(z,lat,lon, patch_based=True):

    x,y = latlon2px(z,lat,lon)
    if patch_based:
        x = int(x/256)#,int(x%256)
        y = int(y/256)#,int(y%256)
    return x,y

def get_cities_by_country(country_names, save_file=None):

    api_entry = 'http://overpass-api.de/api/interpreter?'
    overpass_query = '{0}data=[out:json];area[name="{1}"];(node[place="city"](area););out;'.format(api_entry, urllib2.quote(country_names))
    r = requests.get(overpass_query)
    if r.status_code == 200:
        data = json.loads(r.text)['elements']
        if len(data) == 0:
            logging.warning('OverPass API returns zero result for query "{}"'.format(country_names))
            return None
        if save_file is not None:
            with io.open(save_file, 'wt', encoding='utf8') as fout:
                text = json.dumps(data, indent=4, sort_keys=True, ensure_ascii=False, encoding='utf8')
                fout.write(text)
            logging.info('OverPass JSON data of query "{0}" saved to {1}'.format(country_names, save_file))
        cities = {}
        for city in data:
            cities[city['tags']['name']] = (float(city['lat']), float(city['lon']))
        return cities

    else:
        logging.error('Failed to query from OverPass API')
        return None

def get_bbox_by_city(city_name, country, verify_lat=None, verify_lon=None, epsilon=1e-1):

    '''
        Nominatim API:
        The bounding box format [south_lat, north_lat, west_long, east_long]
    '''
    api_entry = 'http://nominatim.openstreetmap.org/search?'
    osm_query = '{0}city={1}&country={2}&format=json'.format(api_entry, urllib2.quote(city_name), urllib2.quote(country))
    r = requests.get(osm_query)
    if r.status_code == 200:
        data = json.loads(r.text)
        if len(data) == 0:
            logging.error('Empty text returned with query "{}"'.format(city_name))
            return None
        if verify_lat is None and verify_lon is None:
            return data[0]['boundingbox']
        elif verify_lat is not None and verify_lon is not None:
            for city in data:
                bbox = [float(v) for v in city['boundingbox']]
                # print bbox
                lat = float(city['lat'])
                lon = float(city['lon'])
                if math.fabs(verify_lon - lon) < epsilon and math.fabs(verify_lat - lat) < epsilon:
                    return bbox
            logging.error('Approximation check failed of city "{0}" against ({1}, {2})'.format(city, verify_lat, verify_lon))
            return None
    else:
        return None

def gen_bbox_cities_by_country(country, save_file=None):

    locations = {}
    bboxes = {}
    if save_file is not None and os.path.isfile(save_file):
        with open(save_file, 'rt') as fin:
            for line in fin:
                city, lat, lon, south, north, west, east = line.strip().split('\t')
                locations[city] = (float(lat), float(lon))
                bboxes[city] = (float(south), float(north), float(west), float(east))
        return bboxes, locations

    cities = get_cities_by_country(country)
    if cities is not None:
        for city, pos in cities.iteritems():
            bbox = get_bbox_by_city(city.encode('utf8'), country.encode('utf8'), *pos)
            if bbox is not None:
                bboxes[city] = bbox
                locations[city] = pos
                # print('%s - [%f, %f, %f, %f]' % (city, bbox[0], bbox[1], bbox[2], bbox[3]))
            else:
                logging.error('Cannot get bounding box of city "{}" from OSM Nominatim API'.format(city))

        if save_file is not None:
            with open(save_file, 'wt') as fout:
                for city, bb in bboxes.iteritems():
                    pos = locations[city]
                    # print pos
                    # print bb
                    fout.write('{0}\t{1}\t{2}\t{3}\t{4}\t{5}\t{6}\n'.format(city.encode('utf8'), pos[0], pos[1], bb[0], bb[1], bb[2], bb[3]))
            logging.info('Bounding boxes of cities of "{0}" is saved to {1}'.format(country, save_file))
        return bboxes, locations
    else:
        logging.error('Cannot get city list from Overpass API')
        return None, None

# def compute_tiling(bbox, zoom=19):
#
#     lat_start, lat_stop, lon_start, lon_stop = bbox
#     start_x, start_y = latlon2xy(zoom, lat_start, lon_start)
#     stop_x, stop_y = latlon2xy(zoom, lat_stop, lon_stop)
#     return range(start_x, stop_x), range(start_y, stop_y)
#
# def estimate_image_size(bbox, zoom=19):
#
#     lat_patches, lon_patches = compute_tiling(bbox, zoom)
#     num_patches = len(lat_patches) * len(lon_patches)
#     return lat_patches * patch_size, lon_patches * patch_size, num_patches


class EarthMapper(object):

    def __init__(self, patch_size, zoom, directory='.'):

        self.patch_size = patch_size
        self.directory = directory
        self.zoom = zoom

    def world2image(self, lat, lon, zoom):

        raise NotImplementedError

    def image2world(self, x, y, zoom):

        raise NotImplementedError

    def world2grid(self, lat, lon, zoom):

        x, y = self.world2image(lat, lon, zoom)
        return int(x / self.patch_size), int(y / self.patch_size)

    def url(self, lat=None, lon=None, x=None, y=None, bbox=None):

        raise NotImplementedError

    def sampling(self, bbox):

        raise NotImplementedError

    def latitude_per_pixel(self):

        raise NotImplementedError

    def longtitude_per_pixel(self):

        raise NotImplementedError

    def map(self, location, bbox, location_name, max_image_size=None):
        '''
            This function maps a geographical location specified by
            location=(latitude, longtitude), enclosed by a bounding box
            bbox=(south, north, west, east) into a RGB image with maximum size
            is max_image_size=(width, height) whose center is the "location".
            The image is named as "location_name"
        '''
        if max_image_size is not None and bbox is not None:
            assert len(max_image_size) == 2 and [0] > 0 and max_image_size[1] > 0
            bbox = self.shrink_bbox(location, bbox, max_image_size)
        elif max_image_size is not None and bbox is None:
            bbox = self.define_bbox(location, max_image_size)

        samples, w, h = self.sampling(bbox)
        if w*h == 0:
            print 'Invalid bounding box or sampling'
            return
        print len(samples), ',', w, ',', h
        self.download_tiles(samples, location_name)
        self.stitching(w, h, location_name)

    def define_bbox(self, pos, size):

        h, w = size
        lat, lon = pos
        pos_x, pos_y = self.world2image(lat, lon)

        lat_north, lon_west = self.image2world(pos_x - w/2, pos_y - h/2)
        lat_south, lon_east = self.image2world(pos_x + w/2, pos_y + h/2)

        return (lat_south, lat_north, lon_west, lon_east)

    def shrink_bbox(self, pos, bbox, size):
        '''
        Given a bounding box, interpolate an inner bounding box such that
        the corresponding satellite image has size less or equal 'size'
        This function exists because bounding boxes retrieved from OSM or GoogleMaps
        are rather larger than the real size of the urban area of a city.
        '''
        h, w = size
        lat, lon = pos
        pos_x, pos_y = self.world2image(lat, lon)

        lat_south, lat_north, lon_west, lon_east = bbox
        min_x, min_y = self.world2image(lat_north, lon_west)
        max_x, max_y = self.world2image(lat_south, lon_east)

        min_x, max_x = max(min_x, pos_x - w/2), min(max_x, pos_x + w/2)
        min_y, max_y = max(min_y, pos_y - h/2), min(max_y, pos_y + h/2)

        lat_north, lon_west = self.image2world(min_x, min_y)
        lat_south, lon_east = self.image2world(max_x, max_y)
        # lon_west = lon - (pos_x - min_x) * self.longtitude_per_pixel()
        # lon_east = lon + (max_x - pos_x) * self.longtitude_per_pixel()
        # if lon_east > 180.0:
        #     lon_east = - lon_east
        # lat_south = lat - (pos_y - min_y) * self.latitude_per_pixel()
        # lat_north = lat + (max_y - pos_y) * self.latitude_per_pixel()

        return (lat_south, lat_north, lon_west, lon_east)

    def download_tiles(self, samples, location_name):

        user_agent = 'Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10_6_8; de-at) AppleWebKit/533.21.1 (KHTML, like Gecko) Version/5.0.5 Safari/533.21.1'
        headers = { 'User-Agent' : user_agent }

        pbar = ProgressBar(widgets=[SimpleProgress(), ' patches downloaded'], maxval=len(samples)).start()
        i = 0
        for lat, lon in samples:
            url = self.get_url(lat, lon)
            filename = os.path.join(self.directory, "tmp_%s_%d_%d.jpg" % (location_name.encode('utf-8'), self.zoom, i))
            if os.path.isfile(filename):
                continue
            i += 1
            if not os.path.exists(filename):
                bytes = None
                try:
                    req = urllib2.Request(url, data=None, headers=headers)
                    response = urllib2.urlopen(req)
                    bytes = response.read()
                except Exception, e:
                    print "--", url, "->", e
                    pbar.finish()
                    return

                if bytes.startswith("<html>"):
                    print "-- forbidden", filename
                    pbar.finish()
                    return

                f = open(filename,'wb')
                f.write(bytes)
                f.close()

                time.sleep(1 + random.random())
                pbar.update(i)
        pbar.finish()

    def stitching(self, W, H, location_name):

        w, h = W * self.patch_size, H * self.patch_size

        result = Image.new("RGBA", (w, h))

        for y in xrange(H):
            for x in xrange(W):
                filename = os.path.join(self.directory, "tmp_{0}_{1}_{2}.jpg".format(location_name.encode('utf-8'), self.zoom, y*W + x))

                if not os.path.exists(filename):
                    print "-- missing", filename
                    continue

                x_paste = x  * self.patch_size
                y_paste = y * self.patch_size

                try:
                    i = Image.open(filename).crop((0, 30, self.patch_size, self.patch_size + 30))
                except Exception, e:
                    print "-- %s, removing %s" % (e, filename)
                    trash_dst = os.path.expanduser("~/.Trash/%s" % filename)
                    os.rename(filename, trash_dst)
                    continue

                result.paste(i, (x_paste, y_paste))
                os.system(' '.join(['rm', filename]))
                del i

        result.save(os.path.join(self.directory, "map_{0}_z{1}.jpg".format(location_name.encode('utf-8'), self.zoom)))

# class GoogleMaps(EarthMapper):
#
#     def get_url(self, x, y, zoom):
#
#         return "http://mt1.google.com/vt/lyrs=h@162000000&hl=en&x=%d&s=&y=%d&z=%d" % (x, y, zoom)

class BingMaps(EarthMapper):

    lat_limits = (-85.05112878, 85.05112878)

    def __init__(self, zoom, directory, patch_size=256, apikey='Ao25vCxCKEsCjfto3hQYy6Kwvj6Bt35_RoCmLOhndF7YRnv0c982wfx5Wefm9a_S'):

        self.patch_size = patch_size
        self.zoom = zoom
        self.directory = directory
        self.apikey = apikey

    def world2image(self, lat, lon):

        size = 256 * 2**self.zoom
        sin_lat = math.sin(math.radians(lat))
        x = ((lon + 180.0) / 360.0) * size
        y = (0.5 - math.log((1.0 + sin_lat) / (1.0 - sin_lat)) / (4 * math.pi)) * size
        return x, y

    def image2world(self, x, y):

        size = float(256 * 2**self.zoom)
        Z = math.exp(4 * math.pi * (0.5 - float(y) / size))
        lat = -math.degrees(math.asin((1.0 - Z) / (1.0 + Z)))
        # if y > size/2: # below Equator
        #     lat = -lat
        lon = float(x) / size * 360.0 - 180.0
        # if x > size/2: # over Meridian
        #     lon = -lon
        return lat, lon

    def latitude_per_pixel(self):

        return 2*self.lat_limits[1] / (256 * float(2**self.zoom))

    def longtitude_per_pixel(self):

        return 360.0 / (256 * float(2**self.zoom))

    def sampling(self, bbox):

        south, north, west, east = bbox
        left, top = self.world2image(north, west)
        right, bottom = self.world2image(south, east)

        width = int(round((right - left) / float(self.patch_size)))
        height = int(round((bottom - top) / float(self.patch_size)))

        samples = []
        for h in xrange(height):
            for w in xrange(width):
                y = top + (h + 0.5) * self.patch_size
                x = left + (w + 0.5) * self.patch_size
                lat, lon = self.image2world(x, y)
                samples.append((lat, lon))

        return samples, width, height

    def get_url(self, lat, lon):

        return 'http://dev.virtualearth.net/REST/v1/Imagery/Map/Aerial/{0},{1}/{2}?mapSize={3},{4}&key={5}'.format(lat, lon, self.zoom, self.patch_size, self.patch_size+60, self.apikey)

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Download tiled satellite image from Google Maps')
    parser.add_argument('latitude_start', type=float, help='Start latitude value')
    parser.add_argument('longtitude_start', type=float, help='Start longtitude value')
    parser.add_argument('latitude_stop', type=float, help='Stop latitude value')
    parser.add_argument('longtitude_stop', type=float, help='Stop longtitude value')
    parser.add_argument('-z', '--zoom', type=int, default=19, help='Zoom level for the target image')
    parser.add_argument('-g', '--location_name', help='The name of this location', default='')

    args = parser.parse_args()

    download_tiles(args.zoom, args.latitude_start, args.latitude_stop,
                    args.longtitude_start, args.longtitude_stop, satellite=True, location_name=args.location_name)
