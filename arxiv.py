import yaml
import urllib.request, urllib.parse, urllib.error
import feedparser  # version: 5.2.1, other versions may have bugs
from datetime import timedelta, datetime
import argparse
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
# from googletrans import Translator # TODO: may have bugs, try other api
import os
from datetime import datetime


def arxiv_alert(categories=None, keywords=None, authors=None, max_results=1000):
    # API query url for ArXiv
    base_url = 'http://export.arxiv.org/api/query?'

    # Define the query
    search_query = str()
    # set query, categories, keywords, authors
    if categories is not None:
        search_query += '%28'
        for cat in categories:
            search_query += 'cat:%s+OR+' % (cat)
        search_query = search_query[:-4] + '%29'
    if keywords is not None:
        if len(search_query) > 0:
            search_query += '+AND+%28'
        else:
            search_query += '%28'
        for keyw in keywords:
            search_query += 'ti:%s+OR+' % (keyw)
        search_query = search_query[:-4] + '%29+OR+%28'
        for keyw in keywords:
            search_query += 'abs:%s+OR+' % (keyw)
        search_query = search_query[:-4] + '%29'
    if authors is not None:
        if len(search_query) > 0:
            search_query += '+AND+%28'
        else:
            search_query += '%28'
        for author in authors:
            search_query += 'au:%s+OR+' % (author)
        search_query = search_query[:-4] + '%29'
    # set date range
    now = datetime.now()
    end_datetime = now - timedelta(days=2)  # reversely 48 hours
    search_query += '&sortBy=submittedDate&sortOrder=descending'

    # Define numbers of results we want to show
    min_results = 0
    max_results = max_results

    # date-from_date={}&date-to_date={}
    # Wrap up all that in the general query
    query = f'search_query={search_query}&start={min_results}&max_results={max_results}'

    # Use namespaces from Opensearch and ArXiv in feedparser
    feedparser._FeedParserMixin.namespaces['http://a9.com/-/spec/opensearch/1.1/'] = 'opensearch'
    feedparser._FeedParserMixin.namespaces['http://arxiv.org/schemas/atom'] = 'arxiv'

    # Request
    response = urllib.request.urlopen(base_url + query).read()

    # Produce the HTML content
    feed = feedparser.parse(response)
    body = str()
    body += "<link href='https://fonts.googleapis.com/css?family=Montserrat' rel='stylesheet'>"
    body += "<style> \
    body {font-family: 'Montserrat'; background: #F3F3F3; width: 740px; margin: 0 auto; line-height: 150%; margin-top: 50px; font-size: 15px} \
        h1 {font-size: 70px} \
        a {color: #45ABC2} \
        em {font-size: 120%} </style>"
    body += "<h1><center>ArXiv Alert</center></h1>"
    body += f"<font color='#DDAD5C'><em>Daily update: {now.strftime('%d %b %Y')} </em></font>"

    for entry in feed.entries:
        # print(entry)
        published_date = datetime.strptime(entry['published'], '%Y-%m-%dT%H:%M:%SZ')
        if published_date <= end_datetime:
            break

        arxiv_id = entry.id.split('/abs/')[-1]
        if arxiv_id[-2:] != 'v1':
            continue # Only new papers

        pdf_link = ''
        for link in entry.links:
            # use alternate or pdf to link
            if link.rel == 'alternate':
                pdf_link = link.href
                # continue
            elif link.title == 'pdf':
                # pdf_link = link.href
                continue
        body += '<a href="%s"><h2>%s</h2></a>' % (pdf_link, entry.title)

        try:
            body += '<strong><u>Authors:</u></strong>  %s</br>' % ', '.join(author.name for author in entry.authors)
        except AttributeError:
            pass

        # get all the categories
        all_categories = [t['term'] for t in entry.tags]
        body += '<strong><u>Categories:</u></strong> %s</br>' % (', ').join(all_categories)

        # The abstract is in the <summary> element
        # try:
        #     translator = Translator()
        #     entry_summary = translator.translate("%s" % entry.summary, dest='zh-cn') if entry.summary is not None else None
        #     body += '<p><strong><u>Abstract:</u></strong> %s</p>' % entry_summary.text
        # except Exception as e:
        #     print(e)

        body += '<p><strong><u>Abstract:</u></strong> %s</p>' % entry.summary
        body += '</br>'
    body += "</body>"

    return body


# Load config
def load_config(args):
    with open(args.config_path, 'r') as f:
        try:
            config_dict = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            print(exc)
    config_dict['sender'] = os.getenv('SENDER')
    config_dict['password'] = os.getenv('PASSWORD')
    config_dict['receivers'] = os.getenv('RECEIVERS')
    print(type(config_dict['sender']), type(config_dict['password']), type(config_dict['receivers']))
    return config_dict


def process_config(config_dict):
    categories = config_dict['categories'] if 'categories' in config_dict and len(config_dict['categories']) > 0 else None
    keywords = config_dict['keywords'] if 'keywords' in config_dict and len(config_dict['keywords']) > 0 else None
    authors = config_dict['authors'] if 'authors' in config_dict and len(config_dict['authors']) > 0 else None
    max_results = config_dict['max_results']

    def format_phrase(phrases):
        """Format phrases to be used in the query"""
        formatted_phrases = []
        for phrase in phrases:
            phrase = phrase.strip()
            if " " in phrase:  # exact phrase match
                phrase = "%22" + phrase.replace(" ", "+") + "%22"
            formatted_phrases.append(phrase)
        return formatted_phrases

    keywords = format_phrase(keywords) if keywords is not None else None
    authors = format_phrase(authors) if authors is not None else None
    return categories, keywords, authors, max_results


def send_email(body, config_dict):
    now = datetime.now()  # current date and time
    date_time = now.strftime("%m/%d/%Y")
    title = date_time + ' ' + config_dict['mail_title']

    sender = config_dict['sender']
    password = config_dict['password']
    receivers = config_dict['receivers']
    print(len(sender), len(password), len(receivers))
    msg = MIMEMultipart()

    msg['Subject'] = title
    msg.attach(MIMEText(body, 'html'))

    # open smtp first
    smtp_host = config_dict['smtp_host']
    smtp_port = config_dict['smtp_port']

    smtp_obj = smtplib.SMTP_SSL(smtp_host, smtp_port)
    smtp_obj.login(sender, password)
    smtp_obj.sendmail(sender, receivers, msg.as_string())


def save_html(body):
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    year, month, day = timestamp.split('_')[0].split('-')
    if not os.path.exists(year):
        os.mkdir(year)
    if not os.path.exists(os.path.join(year, month)):
        os.mkdir(os.path.join(year, month))
    with open(os.path.join(year, month, timestamp+'.html'), 'w') as f:
        f.write(body)

if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('--config_path', type=str, default='config-demo.yaml')
    args = args.parse_args()

    config_dict = load_config(args)
    categories, keywords, authors, max_results = process_config(config_dict)
    mail_body = arxiv_alert(categories, keywords, authors, max_results)
    send_email(mail_body, config_dict)
