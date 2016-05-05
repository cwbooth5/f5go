[![Build Status](https://travis-ci.org/moronbros/f5go.svg?branch=develop)](https://travis-ci.org/moronbros/f5go) [![Coverage Status](https://coveralls.io/repos/github/moronbros/f5go/badge.svg?branch=master)](https://coveralls.io/github/moronbros/f5go?branch=master)

# The F5 Go Redirector

*A simple service for redirecting mnemonic terms to destination urls.*

Features include:

  - anyone can add terms easily
  - regex parsing for "special cases" (using regular expressions)
  - automatically appends everything after the second slash to the destination url
  - tracks and displays term usage frequency on frontpage with fontsize
  - variables allow destination URLs to change en masse (e.g. project name)

## Required Packages

  - cherrypy
  - jinja2

## Usage

The first order of business is to configure **go.cfg** with custom settings for your redirector. The following are the most important settings to get a redirector running.

Determine what port and protocol(s) the redirector will use. By default, it is going to start a small webserver on port 8080 and use HTTP. This configuration is dictated by the file go.cfg in the project root directory using the variable
**cfg_listenport**.

The config variable **cfg_hostname** is going to default to 'localhost', but it can be set to any IP address of the system.

### Optional Setup Variables
The variable **cfg_fnDatabase** should be a file name ending in .pickle, as this is the serialized data saved by the redirector as it runs. This file is not meant to be edited, loaded, or backed up. If you need to export the database, use 'go.py -e filename.txt' to dump everything from memory into a portable file format.

The variable **cfg_urlFavicon** is a path the an .ico file to be used in the address bar.

The variable **cfg_urlSSO** is an optional authentication URL, usually employed if you need to authenticate users trying to modify redirects.

## Design
The fundamental unit of the Go Redirector is a list of links. A list can have 1 or many links. There are a few behaviors a list of links can have.

Behavior  | Description
------------- | -------------
freshest link  | This is the default. Redirect the user to the most recently-added link.
random link  | Send the user to a random link from the list.
this list | This will always send the user to the *edit page* for this particular redirect.
most used link | This sends the user to the most popular/most used link.
*specific link* | The redirect can also be set up to go to any specific link from the list.


## Unit Testing

Running unit tests is simple. Just go to the project root directory and run:

		tox

This will spin up a little virtualenv, install dependencies, and make sure the code can run in the version(s) of python specified. It will then run a code linter and the unit tests. All problems are shown on the console.

## Tips

To run, execute go.py and go to localhost:8080 in a browser.

backup go database regularly

        $ ./go.py -e your-filename.txt

## Improvements Needed

  - Restoring to a serialized pickle file is prone to corruption. Switch to a proper lightweight DB.
  - Input needs to be properly sanitized for URLS, variables, and list names.

---
contributed by Saul Pwanson

