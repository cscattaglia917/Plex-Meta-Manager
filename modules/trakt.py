import requests, webbrowser
from modules import util
from modules.util import Failed, TimeoutExpired
from ruamel import yaml

logger = util.logger

redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
base_url = "https://api.trakt.tv"
builders = [
    "trakt_list", "trakt_list_details", "trakt_chart", "trakt_userlist", "trakt_boxoffice", "trakt_recommendations",
    "trakt_collected_daily", "trakt_collected_weekly", "trakt_collected_monthly", "trakt_collected_yearly", "trakt_collected_all",
    "trakt_recommended_daily", "trakt_recommended_weekly", "trakt_recommended_monthly", "trakt_recommended_yearly", "trakt_recommended_all",
    "trakt_watched_daily", "trakt_watched_weekly", "trakt_watched_monthly", "trakt_watched_yearly", "trakt_watched_all",
    "trakt_collection", "trakt_popular", "trakt_trending", "trakt_watchlist"
]
sorts = [
    "rank", "added", "title", "released", "runtime", "popularity",
    "percentage", "votes", "random", "my_rating", "watched", "collected"
]
status = ["returning", "production", "planned", "canceled", "ended"]
status_translation = {
    "returning": "returning series", "production": "in production",
    "planned": "planned", "canceled": "canceled", "ended": "ended"
}
periods = ["daily", "weekly", "monthly", "yearly", "all"]
id_translation = {"movie": "movie", "show": "show", "season": "show", "episode": "show", "person": "person", "list": "list"}
id_types = {
    "movie": ("tmdb", "TMDb ID"),
    "person": ("tmdb", "TMDb ID"),
    "show": ("tvdb", "TVDb ID"),
    "season": ("tvdb", "TVDb ID"),
    "episode": ("tvdb", "TVDb ID"),
    "list": ("slug", "Trakt Slug")
}

class Trakt:
    def __init__(self, config, params):
        self.config = config
        self.client_id = params["client_id"]
        self.client_secret = params["client_secret"]
        self.pin = params["pin"]
        self.config_path = params["config_path"]
        self.authorization = params["authorization"]
        logger.secret(self.client_secret)
        if not self._save(self.authorization):
            if not self._refresh():
                self._authorization()
        self._movie_genres = None
        self._show_genres = None
        self._movie_languages = None
        self._show_languages = None
        self._movie_countries = None
        self._show_countries = None
        self._movie_certifications = None
        self._show_certifications = None

    @property
    def movie_genres(self):
        if not self._movie_genres:
            self._movie_genres = [g["slug"] for g in self._request("/genres/movies")]
        return self._movie_genres

    @property
    def show_genres(self):
        if not self._show_genres:
            self._show_genres = [g["slug"] for g in self._request("/genres/shows")]
        return self._show_genres

    @property
    def movie_languages(self):
        if not self._movie_languages:
            self._movie_languages = [g["code"] for g in self._request("/languages/movies")]
        return self._movie_languages

    @property
    def show_languages(self):
        if not self._show_languages:
            self._show_languages = [g["code"] for g in self._request("/languages/shows")]
        return self._show_languages

    @property
    def movie_countries(self):
        if not self._movie_countries:
            self._movie_countries = [g["code"] for g in self._request("/countries/movies")]
        return self._movie_countries

    @property
    def show_countries(self):
        if not self._show_countries:
            self._show_countries = [g["code"] for g in self._request("/countries/shows")]
        return self._show_countries

    @property
    def movie_certifications(self):
        if not self._movie_certifications:
            self._movie_certifications = [g["slug"] for g in self._request("/certifications/movies")["us"]]
        return self._movie_certifications

    @property
    def show_certifications(self):
        if not self._show_certifications:
            self._show_certifications = [g["slug"] for g in self._request("/certifications/shows")["us"]]
        return self._show_certifications

    def _authorization(self):
        if self.pin:
            pin = self.pin
        else:
            url = f"https://trakt.tv/oauth/authorize?response_type=code&redirect_uri={redirect_uri}&client_id={self.client_id}"
            logger.info(f"Navigate to: {url}")
            logger.info("If you get an OAuth error your client_id or client_secret is invalid")
            webbrowser.open(url, new=2)
            try:                                pin = util.logger_input("Trakt pin (case insensitive)", timeout=300).strip()
            except TimeoutExpired:              raise Failed("Input Timeout: Trakt pin required.")
        if not pin:                         raise Failed("Trakt Error: Trakt pin required.")
        json = {
            "code": pin,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }
        response = self.config.post(f"{base_url}/oauth/token", json=json, headers={"Content-Type": "application/json"})
        if response.status_code != 200:
            raise Failed("Trakt Error: Invalid trakt pin. If you're sure you typed it in correctly your client_id or client_secret may be invalid")
        elif not self._save(response.json()):
            raise Failed("Trakt Error: New Authorization Failed")

    def _check(self, authorization=None):
        token = self.authorization['access_token'] if authorization is None else authorization['access_token']
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "trakt-api-version": "2",
            "trakt-api-key": self.client_id
        }
        logger.secret(token)
        response = self.config.get(f"{base_url}/users/settings", headers=headers)
        return response.status_code == 200

    def _refresh(self):
        if self.authorization and "refresh_token" in self.authorization and self.authorization["refresh_token"]:
            logger.info("Refreshing Access Token...")
            json = {
                "refresh_token": self.authorization["refresh_token"],
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "refresh_token"
              }
            response = self.config.post(f"{base_url}/oauth/token", json=json, headers={"Content-Type": "application/json"})
            if response.status_code != 200:
                return False
            return self._save(response.json())
        return False

    def _save(self, authorization):
        if authorization and self._check(authorization):
            if self.authorization != authorization and not self.config.read_only:
                yaml.YAML().allow_duplicate_keys = True
                config, ind, bsi = yaml.util.load_yaml_guess_indent(open(self.config_path, encoding="utf-8"))
                config["trakt"]["pin"] = None
                config["trakt"]["authorization"] = {
                    "access_token": authorization["access_token"],
                    "token_type": authorization["token_type"],
                    "expires_in": authorization["expires_in"],
                    "refresh_token": authorization["refresh_token"],
                    "scope": authorization["scope"],
                    "created_at": authorization["created_at"]
                }
                logger.info(f"Saving authorization information to {self.config_path}")
                yaml.round_trip_dump(config, open(self.config_path, "w"), indent=ind, block_seq_indent=bsi)
                self.authorization = authorization
            return True
        return False

    def _request(self, url, params=None):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.authorization['access_token']}",
            "trakt-api-version": "2",
            "trakt-api-key": self.client_id
        }
        output_json = []
        if params is None:
            params = {}
        pages = 1
        current = 1
        if self.config.trace_mode:
            logger.debug(f"URL: {base_url}{url}")
        while current <= pages:
            if pages == 1:
                response = self.config.get(f"{base_url}{url}", headers=headers, params=params)
                if "X-Pagination-Page-Count" in response.headers and not params:
                    pages = int(response.headers["X-Pagination-Page-Count"])
            else:
                params["page"] = current
                response = self.config.get(f"{base_url}{url}", headers=headers, params=params)
            if response.status_code == 200:
                json_data = response.json()
                if self.config.trace_mode:
                    logger.debug(f"Response: {json_data}")
                if isinstance(json_data, dict):
                    return json_data
                else:
                    output_json.extend(response.json())
            else:
                raise Failed(f"({response.status_code}) {response.reason}")
            current += 1
        return output_json

    def user_ratings(self, is_movie):
        media = "movie" if is_movie else "show"
        id_type = "tmdb" if is_movie else "tvdb"
        return {int(i[media]["ids"][id_type]): i["rating"] for i in self._request(f"/users/me/ratings/{media}s")}

    def convert(self, external_id, from_source, to_source, media_type):
        path = f"/search/{from_source}/{external_id}"
        params = {"type": media_type} if from_source in ["tmdb", "tvdb"] else None
        lookup = self._request(path, params=params)
        if lookup and media_type in lookup[0] and to_source in lookup[0][media_type]["ids"]:
            return lookup[0][media_type]["ids"][to_source]
        raise Failed(f"Trakt Error: No {to_source.upper().replace('B', 'b')} ID found for {from_source.upper().replace('B', 'b')} ID: {external_id}")

    def list_description(self, data):
        try:
            return self._request(requests.utils.urlparse(data).path)["description"]
        except Failed:
            raise Failed(f"Trakt Error: List {data} not found")

    def _parse(self, items, typeless=False, item_type=None):
        ids = []
        for item in items:
            if typeless:
                data = item
                current_type = item_type
            elif item_type:
                data = item[item_type]
                current_type = item_type
            elif "type" in item and item["type"] in id_translation:
                data = item[id_translation[item["type"]]]
                current_type = item["type"]
            else:
                continue
            id_type, id_display = id_types[current_type]
            if id_type in data["ids"] and data["ids"][id_type]:
                final_id = data["ids"][id_type]
                if current_type == "episode":
                    final_id = f"{final_id}_{item[current_type]['season']}"
                if current_type in ["episode", "season"]:
                    final_id = f"{final_id}_{item[current_type]['number']}"
                if current_type in ["person", "list"]:
                    final_id = (final_id, data["name"])
                final_type = f"{id_type}_{current_type}" if current_type in ["episode", "season", "person"] else id_type
                ids.append((final_id, final_type))
            else:
                name = data["name"] if current_type in ["person", "list"] else f"{data['title']} ({data['year']})"
                logger.error(f"Trakt Error: No {id_display} found for {name}")
        return ids

    def all_user_lists(self, user):
        try:
            items = self._request(f"/users/{user}/lists")
        except Failed:
            raise Failed(f"Trakt Error: User {user} not found")
        if len(items) == 0:
            raise Failed(f"Trakt Error: User {user} has no lists")
        return {self.build_user_url(user, i["ids"]["slug"]): i["name"] for i in items}

    def all_liked_lists(self):
        items = self._request(f"/users/likes/lists")
        if len(items) == 0:
            raise Failed(f"Trakt Error: No Liked lists found")
        return {self.build_user_url(i['list']['user']['ids']['slug'], i['list']['ids']['slug']): i["list"]["name"] for i in items}

    def build_user_url(self, user, name):
        return f"{base_url.replace('api.', '')}/users/{user}/lists/{name}"

    def _list(self, data):
        try:
            items = self._request(f"{requests.utils.urlparse(data).path}/items")
        except Failed:
            raise Failed(f"Trakt Error: List {data} not found")
        if len(items) == 0:
            raise Failed(f"Trakt Error: List {data} is empty")
        return self._parse(items)

    def _userlist(self, list_type, user, is_movie, sort_by=None):
        try:
            url_end = "movies" if is_movie else "shows"
            if sort_by:
                url_end = f"{url_end}/{sort_by}"
            items = self._request(f"/users/{user}/{list_type}/{url_end}")
        except Failed:
            raise Failed(f"Trakt Error: User {user} not found")
        if len(items) == 0:
            raise Failed(f"Trakt Error: {user}'s {list_type.capitalize()} is empty")
        return self._parse(items, item_type="movie" if is_movie else "show")

    def _recommendations(self, limit, is_movie):
        media_type = "Movie" if is_movie else "Show"
        try:
            items = self._request(f"/recommendations/{'movies' if is_movie else 'shows'}", params={"limit": limit})
        except Failed:
            raise Failed(f"Trakt Error: failed to fetch {media_type} Recommendations")
        if len(items) == 0:
            raise Failed(f"Trakt Error: no {media_type} Recommendations were found")
        return self._parse(items, typeless=True, item_type="movie" if is_movie else "show")

    def _charts(self, chart_type, is_movie, params, time_period=None):
        chart_url = f"{chart_type}/{time_period}" if time_period else chart_type
        items = self._request(f"/{'movies' if is_movie else 'shows'}/{chart_url}", params=params)
        return self._parse(items, typeless=chart_type == "popular", item_type="movie" if is_movie else "show")

    def get_people(self, data):
        return {str(i[0][0]): i[0][1] for i in self._list(data) if i[1] == "tmdb_person"}

    def validate_list(self, trakt_lists):
        values = util.get_list(trakt_lists, split=False)
        trakt_values = []
        for value in values:
            if isinstance(value, dict):
                raise Failed("Trakt Error: List cannot be a dictionary")
            try:
                self._list(value)
                trakt_values.append(value)
            except Failed as e:
                logger.error(e)
        if len(trakt_values) == 0:
            raise Failed(f"Trakt Error: No valid Trakt Lists in {values}")
        return trakt_values

    def validate_chart(self, err_type, method_name, data, is_movie):
        valid_dicts = []
        for trakt_dict in util.get_list(data, split=False):
            if not isinstance(trakt_dict, dict):
                raise Failed(f"{err_type} Error: {method_name} must be a dictionary")
            dict_methods = {dm.lower(): dm for dm in trakt_dict}
            try:
                if method_name == "trakt_chart":
                    final_dict = {}
                    final_dict["chart"] = util.parse(err_type, "chart", trakt_dict, methods=dict_methods, parent=method_name, options=["recommended", "watched", "collected", "trending", "popular"])
                    final_dict["limit"] = util.parse(err_type, "limit", trakt_dict, methods=dict_methods, parent=method_name, datatype="int", default=10)
                    final_dict["time_period"] = None
                    if final_dict["chart"] in ["recommended", "watched", "collected"] and "time_period" in dict_methods:
                        final_dict["time_period"] = util.parse(err_type, "time_period", trakt_dict, methods=dict_methods, parent=method_name, default="weekly", options=periods)
                    if "query" in dict_methods:
                        final_dict["query"] = util.parse(err_type, "query", trakt_dict, methods=dict_methods, parent=method_name)
                    if "year" in dict_methods:
                        try:
                            if trakt_dict[dict_methods["year"]] and len(str(trakt_dict[dict_methods["year"]])) == 4:
                                final_dict["year"] = util.parse(err_type, "year", trakt_dict, methods=dict_methods, parent=method_name, datatype="int", minimum=1000, maximum=3000)
                            else:
                                final_dict["year"] = util.parse(err_type, "year", trakt_dict, methods=dict_methods, parent=method_name, datatype="int", minimum=1000, maximum=3000, range_split="-")
                        except Failed:
                            raise Failed(f"{err_type} Error: trakt_chart year attribute must be either a 4 digit year or a range of two 4 digit year with a '-' i.e. 1950 or 1950-1959")
                    if "runtimes" in dict_methods:
                        final_dict["runtimes"] = util.parse(err_type, "runtimes", trakt_dict, methods=dict_methods, parent=method_name, datatype="int", range_split="-")
                    if "ratings" in dict_methods:
                        final_dict["ratings"] = util.parse(err_type, "ratings", trakt_dict, methods=dict_methods, parent=method_name, datatype="int", minimum=0, maximum=100, range_split="-")
                    if "genres" in dict_methods:
                        final_dict["genres"] = util.parse(err_type, "genres", trakt_dict, methods=dict_methods, parent=method_name, datatype="list", options=self.movie_genres if is_movie else self.show_genres)
                    if "languages" in dict_methods:
                        final_dict["languages"] = util.parse(err_type, "languages", trakt_dict, methods=dict_methods, parent=method_name, datatype="list", options=self.movie_languages if is_movie else self.show_languages)
                    if "countries" in dict_methods:
                        final_dict["countries"] = util.parse(err_type, "countries", trakt_dict, methods=dict_methods, parent=method_name, datatype="list", options=self.movie_countries if is_movie else self.show_countries)
                    if "certifications" in dict_methods:
                        final_dict["certifications"] = util.parse(err_type, "certifications", trakt_dict, methods=dict_methods, parent=method_name, datatype="list", options=self.movie_certifications if is_movie else self.show_certifications)
                    if "networks" in dict_methods and not is_movie:
                        final_dict["networks"] = util.parse(err_type, "networks", trakt_dict, methods=dict_methods, parent=method_name, datatype="list")
                    if "status" in dict_methods and not is_movie:
                        final_dict["status"] = util.parse(err_type, "status", trakt_dict, methods=dict_methods, parent=method_name, datatype="list", options=status)
                    valid_dicts.append(final_dict)
                else:
                    userlist = util.parse(err_type, "userlist", trakt_dict, methods=dict_methods, parent=method_name, options=["recommended", "watched", "collected", "watchlist"])
                    user = util.parse(err_type, "user", trakt_dict, methods=dict_methods, parent=method_name, default="me")
                    sort_by = None
                    if userlist in ["recommended", "watchlist"] and "sort" in dict_methods:
                        sort_by = util.parse(err_type, "sort_by", trakt_dict, methods=dict_methods, parent=method_name, default="rank", options=["rank", "added", "released", "title"])
                    self._userlist("collection" if userlist == "collected" else userlist, user, is_movie, sort_by=sort_by)
                    valid_dicts.append({"userlist": userlist, "user": user, "sort_by": sort_by})
            except Failed as e:
                logger.error(e)
        if len(valid_dicts) == 0:
            raise Failed(f"Trakt Error: No valid Trakt {method_name[6:].capitalize()}")
        return valid_dicts

    def get_trakt_ids(self, method, data, is_movie):
        pretty = method.replace("_", " ").title()
        media_type = "Movie" if is_movie else "Show"
        if method == "trakt_list":
            logger.info(f"Processing {pretty}: {data}")
            return self._list(data)
        elif method == "trakt_recommendations":
            logger.info(f"Processing {pretty}: {data} {media_type}{'' if data == 1 else 's'}")
            return self._recommendations(data, is_movie)
        elif method == "trakt_chart":
            params = {"limit": data["limit"]}
            chart_limit = f"{data['limit']} {data['time_period'].capitalize()}" if data["time_period"] else data["limit"]
            logger.info(f"Processing {pretty}: {chart_limit} {data['chart'].capitalize()} {media_type}{'' if data == 1 else 's'}")
            for attr in ["query", "year", "runtimes", "ratings", "genres", "languages", "countries", "certifications", "networks", "status"]:
                if attr in data:
                    logger.info(f"{attr:>22}: {','.join(data[attr]) if isinstance(data[attr], list) else data[attr]}")
                    values = [status_translation[v] for v in data[attr]] if attr == "status" else data[attr]
                    params[attr] = ",".join(values) if isinstance(values, list) else values
            return self._charts(data["chart"], is_movie, params, time_period=data["time_period"])
        elif method == "trakt_userlist":
            logger.info(f"Processing {pretty} {media_type}s from {data['user']}'s {data['userlist'].capitalize()}")
            return self._userlist(data["userlist"], data["user"], is_movie, sort_by=data["sort_by"])
        else:
            raise Failed(f"Trakt Error: Method {method} not supported")
