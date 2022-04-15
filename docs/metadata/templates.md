# Templates

Collections often share a lot of common [or generalizable] configuration details.  Templates allow you to define these details so they can be used across multiple collections.

For example, an actor collection might look like this:

```yaml
collections:
  Bruce Lee:
    actor: tmdb
    tmdb_person: 19429
    sort_title: +_Bruce Lee
    sync_mode: sync
    collection_order: release
```

Then you add another:

```
collections:
  Bruce Lee:
    actor: tmdb
    tmdb_person: 19429
    sort_title: +_Bruce Lee
    sync_mode: sync
    collection_order: release
  Chris Pratt:
    actor: tmdb
    tmdb_person: 73457
    sort_title: +_Chris Pratt
    sync_mode: sync
    collection_order: release
```

You could keep going in this way, but there's a lot of repetition there.  Both of these collections have the same `sync_mode`, `collection_order`, and `actor` settings; the other two details, `tmdb_person` and `sort_title`, depend on a value defined in the collection.

Those repetitive aspects can be moved into template and leveraged by multiple collections.

For example, a template for those two collections might look like this:

```yaml
templates:
  Actor:
    actor: tmdb
    tmdb_person: <<person>>
    sort_title: +_<<collection_name>>
    sync_mode: sync
    collection_order: release
```

The only things that change are the ID that is used with `tmdb_person` and the name of the collection that is used in `sort_title`.

Those two things surrounded by `<< >>` are "template variables" that you can define for any collection using this template, like this:

```yaml
collections:
  Bruce Lee:
    template: {name: Actor, person: 19429}
```

or as a list:

```yaml
collections:
  Chris Pratt:
    template:
      name: Actor
      person: 73457
```

Note that we provide the template name ["Actor"] and the value to insert in the place of `<<person>>`.  The `<<collection_name>>` is a required property of a collection, so it is always available and doesn't have to be called out like `<<person>>`.

Inside a template, you can use all the Builders, Details, and [Filters](filters) attributes that you can give collections/playlists [except `template`; templates cannot be nested].

The names of template variables that you define are arbitrary.  In the example above, `<<person>>` could have been `<<tvdb_person_id>>` or `<<bing>>` or anything else.  The only thing that matters is that in the template definition you surround them with `<< >>` and in the collection definition you spell it correctly.

To use a template with a collection definition you use the `template` attribute. The only required attribute under `template` is `name` which must correspond exactly to the template mapping name. Any other attributes under `template` are considered template variables whose names correspond exactly with the template variable name surrounded by `<<` and `>>` in the templates. These template variables will replace any part of any value that contains the template variable name surrounded by `<<` and `>>` in the template with the specified template variable's value.

Here's the full example Actor template and two different ways to use it, as it would appear in a metadata file.

```yaml
templates:
  Actor:
    actor: tmdb
    tmdb_person: <<person>>
    sort_title: +_<<collection_name>>
    sync_mode: sync
    collection_order: release
collections:
  Bruce Lee:
    template: {name: Actor, person: 19429}
  Chris Pratt:
    template:
      name: Actor
      person: 73457
```

There are three attributes unique to `templates`, `default`, `optional`, and `move_prefix`.

* `default` can set default values for template variables to be used if they're not specified in the call.
* `optional` can specify variables that if not specified on the template call will cause any attribute using one of those variables to be ignored in the template. You can make any template variable optional per collection by setting it to `null`.
* `move_prefix` can be given a list or comma-separated string of prefixes to move to the end of the collection/playlist name for sorting.
    i.e. If you have `move_prefix: The` and a collection is called `The Avengers` then `<<collection_name>>` is replaced with `Avengers, The` instead of `The Avengers` for that collection.

Here's an example IMDb Genre template and two different ways to call it.

```yaml
templates:
  IMDb Genre:
    default:
      title: feature
      limit: 100
    optional:
      - poster_id
    imdb_list:
    - url: https://www.imdb.com/search/title/?title_type=<<title>>&release_date=1990-01-01,&user_rating=5.0,10.0&num_votes=100000,&genres=<<genre>>
      limit: <<limit>>
    - url: https://www.imdb.com/search/title/?title_type=<<title>>&release_date=1990-01-01,&user_rating=5.0,10.0&num_votes=100000,&genres=<<genre>>&sort=user_rating,desc
      limit: <<limit>>
    sort_title: ++_<<collection_name>>
    url_poster: https://theposterdb.com/api/assets/<<poster_id>>
    sync_mode: sync
    collection_order: alpha
collections:
  Action:
    template:
      name: IMDb Genre
      genre: action
    summary: Action film is a genre wherein physical action takes precedence in the storytelling. The film will often have continuous motion and action including physical stunts, chases, fights, battles, and races. The story usually revolves around a hero that has a goal, but is facing incredible odds to obtain it.
  Comedy:
    template: {name: IMDb Genre, genre: comedy, poster_id: 69200}
    summary: Comedy is a genre of film that uses humor as a driving force. The aim of a comedy film is to illicit laughter from the audience through entertaining stories and characters. Although the comedy film may take on some serious material, most have a happy ending. Comedy film has the tendency to become a hybrid sub-genre because humor can be incorporated into many other genres. Comedies are more likely than other films to fall back on the success and popularity of an individual star.
  Romantic Comedy:
    template: {name: IMDb Genre, genre: "romance,comedy", limit: 200}
    summary: Romantic Comedy is a genre that attempts to catch the viewer’s heart with the combination of love and humor. This sub-genre is light-hearted and usually places the two protagonists in humorus situation. Romantic-Comedy film revolves around a romantic ideal, such as true love. In the end, the ideal triumphs over the situation or obstacle, thus creating a happy ending.
    filters:
      genre: Comedy
```

Check out the example files in the [Plex Meta Manager Configs Repository](https://github.com/meisnate12/Plex-Meta-Manager-Configs/tree/master/meisnate12) for more uses and examples.
