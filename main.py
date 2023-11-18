import os
import sys
from typing import Optional, Dict, Any, List, Union
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import threading


class WebPageFetcher:
    """
    A class for fetching web pages and saving them to disk with metadata and a local mirror.
    """

    def __init__(self) -> None:
        """
        Initializes the WebPageFetcher object.
        """
        self.metadata: Dict[str, Any] = {}
        self.lock = threading.Lock()

    def fetch_content(self, url: str, as_bytes: bool = False) -> Optional[Union[str, bytes]]:
        """
        Fetches the content of a given URL.

        Args:
            url (str): The URL to fetch.
            as_bytes (bool): If True, returns content as bytes. If False, returns as text.

        Returns:
            Optional[Union[str, bytes]]: The content if successful, else None.
        """
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.content if as_bytes else response.text
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None

    def create_directory(self, url: str) -> None:
        """
        Creates a directory named after the URL to store assets.

        Args:
            url (str): The URL for which the directory will be created.
        """
        dir_name = self.get_directory_name(url)
        os.makedirs(dir_name, exist_ok=True)

    def get_directory_name(self, url: str) -> str:
        """
        Generates a directory name based on the URL.

        Args:
            url (str): The URL to generate a directory name for.

        Returns:
            str: The directory name.
        """
        parsed_url = urlparse(url)
        return os.path.join(os.getcwd(), parsed_url.netloc, os.path.dirname(parsed_url.path).lstrip('/'))

    def remove_leading_slash(self, content: Union[str, bytes], tags: list[str]) -> Union[str, bytes]:
        """
        Remove the leading "/" from the path of specified tags in the content.

        Args:
            content (Union[str, bytes]): The content to modify.
            tags (list[str]): The list of tags to modify.

        Returns:
            Union[str, bytes]: The modified content.
        """
        soup = BeautifulSoup(content, 'html.parser')
        for tag_name in tags:
            for tag in soup.find_all(tag_name, href=True) + soup.find_all(tag_name, src=True):
                tag['href' if 'href' in tag.attrs else 'src'] = tag['href' if 'href' in tag.attrs else 'src'].lstrip(
                    '/')

        return str(soup)

    def save_to_file(self, url: str, content: str, base_url: str) -> str:
        """
        Saves HTML content and assets to a file, creating a local mirror.

        Args:
            url (str): The URL of the web page.
            content (str): The HTML content to save.
            base_url (str): The base URL to resolve relative URLs.

        Returns:
            str: The filename where the content is saved.
        """
        self.create_directory(url)
        file_name = os.path.join(self.get_directory_name(url), "index.html")
        with open(file_name, "wb" if isinstance(content, bytes) else "w", encoding="utf-8") as file:
            # Remove the leading "/" from the path of all "<link href" and "<script src"
            content = self.remove_leading_slash(content, ['link', 'script', 'img'])
            file.write(content)

        # Download and save assets
        soup = BeautifulSoup(content, 'html.parser')
        threads = []
        for tag in soup(['script', 'link', 'img'], href=True) + soup(['script', 'link', 'img'], src=True):
            asset_url = urljoin(base_url, tag.get('href') or tag.get('src'))
            thread = threading.Thread(target=self.download_asset, args=(asset_url, url))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        return file_name

    def download_asset(self, asset_url: str, base_url: str) -> None:
        """
        Downloads an asset and saves it to the local directory.

        Args:
            asset_url (str): The URL of the asset to download.
            base_url (str): The base URL for which the directory was created.
        """
        asset_content = self.fetch_content(asset_url, as_bytes=True)
        if asset_content:
            asset_file_path = os.path.join(self.get_directory_name(asset_url), os.path.basename(asset_url))

            # Ensure the directory exists before saving the asset
            os.makedirs(os.path.dirname(asset_file_path), exist_ok=True)

            with open(asset_file_path, 'wb') as asset_file:
                asset_file.write(asset_content)
            with self.lock:
                print(f"Downloaded asset: {asset_url}")

    def get_metadata(self, html_content: str) -> None:
        """
        Extracts metadata from HTML content.

        Args:
            html_content (str): The HTML content to extract metadata from.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        links = soup.find_all('a')
        images = soup.find_all('img')

        self.metadata = {
            'num_links': len(links),
            'images': len(images),
            'last_fetch': datetime.utcnow().strftime('%a %b %d %Y %H:%M:%S UTC')
        }

    def print_metadata(self) -> None:
        """
        Prints the fetched metadata.
        """
        print("Metadata:")
        for key, value in self.metadata.items():
            print(f"{key}: {value}")

    def download_and_print_metadata(self, urls: List[str], with_metadata: bool) -> None:
        """
        Downloads web pages, saves to disk, and prints metadata.

        Args:
            urls (List[str]): List of URLs to fetch.
            with_metadata (bool): Flag to indicate whether to print metadata.
        """
        threads = []

        for url in urls:
            thread = threading.Thread(target=self.process_url, args=(url, with_metadata))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

    def process_url(self, url: str, with_metadata: bool) -> None:
        """
        Processes a URL, downloads the web page, and saves to disk.

        Args:
            url (str): The URL to fetch.
            with_metadata (bool): Flag to indicate whether to print metadata.
        """
        html_content = self.fetch_content(url)

        if html_content is not None:
            file_name = self.save_to_file(url, html_content, url)
            with self.lock:
                print(f"Downloaded {url} to {file_name}")

            if with_metadata:
                self.get_metadata(html_content)
                with self.lock:
                    self.print_metadata()


def main() -> None:
    """
    Main entry point for the script.
    """
    if len(sys.argv) < 2:
        print("Usage: python3 main.py  [--metadata] url1 [url2 ...]")
        sys.exit(1)

    urls = sys.argv[2:]
    with_metadata = "--metadata" in sys.argv

    fetcher = WebPageFetcher()
    fetcher.download_and_print_metadata(urls, with_metadata)


if __name__ == "__main__":
    main()
