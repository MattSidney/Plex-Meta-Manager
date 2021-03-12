import logging, requests
from lxml import html
from modules import util
from modules.util import Failed
from retrying import retry

logger = logging.getLogger("Plex Meta Manager")

class LetterboxdAPI:
    def __init__(self, config):
        self.config = config
        self.url = "https://letterboxd.com"

    @retry(stop_max_attempt_number=6, wait_fixed=10000)
    def send_request(self, url, language):
        return html.fromstring(requests.get(url, headers={"Accept-Language": language, "User-Agent": "Mozilla/5.0 x64"}).content)

    def get_list_description(self, list_url, language):
        descriptions = self.send_request(list_url, language).xpath("//meta[@property='og:description']/@content")
        return descriptions[0] if len(descriptions) > 0 and len(descriptions[0]) > 0 else None

    def parse_list(self, list_url, language):
        response = self.send_request(list_url, language)
        letterboxd_ids = response.xpath("//div[@class='poster film-poster really-lazy-load']/@data-film-id")
        items = []
        for letterboxd_id in letterboxd_ids:
            slugs = response.xpath(f"//div[@data-film-id='{letterboxd_id}']/@data-film-slug")
            items.append((letterboxd_id, slugs[0]))
        next_url = response.xpath("//a[@class='next']/@href")
        if len(next_url) > 0:
            items.extend(self.parse_list(f"{self.url}{next_url[0]}", language))
        return items

    def get_tmdb_from_slug(self, slug, language):
        return self.get_tmdb(f"{self.url}{slug}", language)

    def get_tmdb(self, letterboxd_url, language):
        response = self.send_request(letterboxd_url, language)
        ids = response.xpath("//a[@data-track-action='TMDb']/@href")
        if len(ids) > 0 and ids[0]:
            if "themoviedb.org/movie" in ids[0]:
                return util.regex_first_int(ids[0], "TMDB Movie ID")
            raise Failed(f"Letterboxd Error: TMDb Movie ID not found in {ids[0]}")
        raise Failed(f"Letterboxd Error: TMDb Movie ID not found at {letterboxd_url}")

    def get_items(self, method, data, language, status_message=True):
        pretty = util.pretty_names[method] if method in util.pretty_names else method
        movie_ids = []
        if status_message:
            logger.info(f"Processing {pretty}: {data}")
        items = self.parse_list(data, language)
        total_items = len(items)
        if total_items == 0:
            raise Failed(f"Letterboxd Error: No List Items found in {data}")
        length = 0
        for i, item in enumerate(items, 1):
            length = util.print_return(length, f"Finding TMDb ID {i}/{total_items}")
            tmdb_id = None
            expired = None
            if self.config.Cache:
                tmdb_id, expired = self.config.Cache.query_letterboxd_map(item[0])
            if not tmdb_id or expired is not False:
                try:
                    tmdb_id = self.get_tmdb_from_slug(item[1], language)
                except Failed as e:
                    logger.error(e)
                    continue
                if self.config.ache:
                    self.config.Cache.update_letterboxd(expired, item[0], tmdb_id)
            movie_ids.append(tmdb_id)
        util.print_end(length, f"Processed {total_items} TMDb IDs")
        if status_message:
            logger.debug(f"TMDb IDs Found: {movie_ids}")
        return movie_ids, []
