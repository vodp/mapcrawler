import os
import json
from mapping import *

def test__get_cities_by_country():

	cities = get_cities_by_country('France')
	assert cities is not None and len(cities) > 0, 'Do not get any city with country "France"'

	cities = get_cities_by_country('abc')
	assert cities is None, "Returned result should be None"

	cities = get_cities_by_country('France', 'countries.json')
	if os.path.isfile('countries.json'):
		data = json.load('countries.json')
		assert len(cities) == len(data), "Written JSON data is inconsistent with retrieved data"
	else:
		raise Error('"countries.json" not exist')
	return True

def test__get_bbox_by_city():

	city_name = 'Paris'
	country = 'France'

	cities = get_cities_by_country(country)
	assert cities is not None, 'Cannot retrieve from OSM'
	if city_name in cities.keys():
		lat, lon = cities[city_name]
		bbox = get_bbox_by_city(city_name, country, lat, lon)
		assert len(bbox) == 4
		print(bbox)
	else:
		raise Error('"Paris" not present in cities of "France"')
