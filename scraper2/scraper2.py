__author__ = "Sam Maurer, UrbanSim Inc"
__date__ = "May 4, 2016"

import datetime as dt
import urllib
import unicodecsv as csv
from lxml import html
import requests


# Some defaults, which can be overridden when the class is called

DOMAINS = ['http://atlanta.craigslist.org']
OUTFILE = 'data/test.csv'
# These timestamps will be interpreted locally to the listing location
EARLIEST_TS = dt.datetime.now() - dt.timedelta(hours=1)
LATEST_TS = dt.datetime.now()


class RentalListingScraper(object):

	def __init__(
			self, 
			domains = DOMAINS, 
			outfile = OUTFILE,
			earliest_ts = EARLIEST_TS,
			latest_ts = LATEST_TS):
		
		self.domains = domains
		self.outfile = outfile
		self.earliest_ts = earliest_ts
		self.latest_ts = latest_ts


	def _get_str(self, list):
		'''
		The xpath() function returns a list of items that may be empty. Most of the time,
		we want the first of any strings that match the xml query. This helper function
		returns that string, or null if the list is empty.
		'''
		
		if len(list) > 0:
			return list[0]

		return ''
	
	
	def _get_int_prefix(self, str, label):
		'''
		Bedrooms and square footage have the format "xx 1br xx 450ft xx". This helper 
		function extracts relevant integers from strings of this format.
		'''		
		
		for s in str.split(' '):
			if label in s:
				return s.strip(label)
				
		return 0
		

	def _parseListing(self, item):
		'''
		Note that xpath() returns a list with elements of varying types depending on the
		query results: xml objects, strings, etc.
		'''
	
		pid = item.xpath('@data-pid')[0]  # post id, always present
	
		# Extract two lines of listing info, always present
		line1 = item.xpath('span[@class="txt"]/span[@class="pl"]')[0]
		line2 = item.xpath('span[@class="txt"]/span[@class="l2"]')[0]
	
		dt = line1.xpath('time/@datetime')[0]  # always present
		url = line1.xpath('a/@href')[0]  # always present
		title = self._get_str(line1.xpath('a/span/text()'))
	
		price = self._get_str(line2.xpath('span[@class="price"]/text()')).strip('$')
		neighb = self._get_str(line2.xpath('span[@class="pnr"]/small/text()')).strip(' ()')
		bedsqft = self._get_str(line2.xpath('span[@class="housing"]/text()'))
	
		beds = self._get_int_prefix(bedsqft, "br")  # appears as "1br" to "8br" or missing
		sqft = self._get_int_prefix(bedsqft, "ft")  # appears as "000ft" or missing
		
		return [pid, dt, url, title, price, neighb, beds, sqft]
		

	def _parseAddress(self, tree):
		'''
		Some listings include an address, but we have to parse it out of an encoded
		Google Maps url.
		'''
		url = self._get_str(tree.xpath('//p[@class="mapaddress"]/small/a/@href'))
		
		if '?q=loc' not in url:
			# That string precedes an address search
			return ''
			
		return urllib.unquote_plus(url.split('?q=loc')[1]).strip(' :')

	
	def _scrapeLatLng(self, url):
	
		page = requests.get(url)
		tree = html.fromstring(page.content)
		
		map = tree.xpath('//div[@id="map"]')

		# Sometimes there's no location info, and no map on the page		
		if len(map) == 0:
			return ['', '', '', '']

		map = map[0]
		lat = map.xpath('@data-latitude')[0]
		lng = map.xpath('@data-longitude')[0]
		accuracy = map.xpath('@data-accuracy')[0]
		address = self._parseAddress(tree)
		
		return [lat, lng, accuracy, address]
		
	
	def run(self):
	
		colnames = ['pid','dt','url','title','price','neighb','beds','sqft',
						'lat','lng','accuracy','address']

		with open(self.outfile, 'wb') as f:
			writer = csv.writer(f)
			writer.writerow(colnames)

			# Loop over each regional Craigslist URL
			for domain in self.domains:
			
				regionIsComplete = False
				page = requests.get(domain + '/search/apa')  # Initial page of search results
				
				while not regionIsComplete:
					tree = html.fromstring(page.content)
					# Each listing on the search results page is labeled as <p class="row">
					listings = tree.xpath('//p[@class="row"]')

					for item in listings:
						row = self._parseListing(item)
						ts = dt.datetime.strptime(row[1], '%Y-%m-%d %H:%M')
				
						if (ts > self.latest_ts):
							# Skip this row, but continue searching the same region
							break
					
						if (ts < self.earliest_ts):
							# Move on to the next region
							regionIsComplete = True
							break 
					
						row[2] = domain + row[2]  # Insert regional Craigslist domain
						row += self._scrapeLatLng(row[2])
				
						writer.writerow(row)
						
					# Go to the next search results page
					next = tree.xpath('//a[@title="next page"]/@href')
					if len(next) > 0:
						page = requests.get(domain + next[0])
					else:
						regionIsComplete = True
							
		return


