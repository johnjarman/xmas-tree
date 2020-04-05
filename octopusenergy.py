"""
Get electricity prices from Octopus Energy API.

John Jarman johncjarman@gmail.com
"""

import logging
import json
import requests
from datetime import datetime

class CurrentPriceNotFoundError(Exception):
    pass

def load_api_key_from_file(filename):
    with open(filename) as f:
        s = f.read()
        return s.strip()

class OctopusEnergy:
    def __init__(self, api_key, cache_file='cache.json'):
        self.api_key = api_key
        self.cache_file = cache_file
        self.api_url = 'https://api.octopus.energy/v1/products/AGILE-18-02-21/electricity-tariffs/E-1R-AGILE-18-02-21-A/standard-unit-rates/'
        self.date_format = '%Y-%m-%dT%H:%M:%SZ'

    def get_elec_price(self, cache=True):
        """ Get current electricity price 
        @param bool cache: Allow caching of fetched values
        """
        price = None

        if cache:
            try:
                with open(self.cache_file) as f:
                    # Load cached data from file
                    data = json.load(f)

                    # Retrieve current price
                    price = self._get_current_price_from_data(data)

            except FileNotFoundError:
                logging.warn('Cache file {} not found'.format(self.cache_file))

            except (CurrentPriceNotFoundError, json.JSONDecodeError) as err:
                logging.info('Cache miss, loading from HTTP. {}'.format(err))
        
        if price is None:
            # Cache miss, get price via HTTP
            data = self._get_data_http()
            price = self._get_current_price_from_data(data)

        return price

    def _get_data_http(self):
        r = requests.get(self.api_url, auth=(self.api_key + ':', ''))
        data = json.loads(r.text)
        # Write latest data to cache file
        with open(self.cache_file, 'w') as f:
            f.write(r.text)
            logging.info('HTTP data written to cache file {}'.format(self.cache_file))
        return data

    def _get_current_price_from_data(self, data):
        current_time = datetime.now()
        price = None
        try:
            for val in data['results']:
                if (datetime.strptime(val['valid_from'], self.date_format) <= current_time and
                    datetime.strptime(val['valid_to'], self.date_format) > current_time):
                    price = val['value_exc_vat']
        except KeyError:
            logging.error("Could not get price data: " + data['detail'])

        if price is None:
            raise CurrentPriceNotFoundError
        
        return price

if __name__ == '__main__':
    api_key = load_api_key_from_file('api_key.txt')
    oe = OctopusEnergy(api_key)
    print(oe.get_elec_price())