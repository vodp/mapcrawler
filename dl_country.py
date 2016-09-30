import os
import sys
import mapping

reload(sys)
sys.setdefaultencoding('utf8')

country = sys.argv[1] #'Ireland'
img_size = (256*18, 256*18)
zoom = 16
data_dir = '/amy/dcgan_sat/images'
bbs, locs = mapping.gen_bbox_cities_by_country(country, save_file='%s.txt' % (country))
assert bbs is not None
assert locs is not None
print 'Total %d cities rertieved' % (len(locs))

mapper = mapping.BingMaps(zoom, data_dir, 256*3)
for city, bb in bbs.iteritems():
    # cities = city.split('./:-')
    loc = locs[city]
    # if len(cities) > 1:
        # city = cities[-1]

    fname = os.path.join(data_dir, "map_{0}_z{1}.jpg".format(city.replace('/', '-'), zoom))
    if os.path.isfile(fname):
        continue
    print u'Mapping city {0} at ({1}, {2})...'.format(city, loc[0], loc[1])
    # specifying img_size will often shrink the bounding box to maximum image dimensions
    # new_bbox = mapper.shrink_bbox(loc, bb, img_size)
    mapper.map(loc, None, city.decode('utf8').replace('/', '-'), [dim*2 for dim in img_size])
#    mapper.map(loc, None, city.replace('/', '-'), img_size)
