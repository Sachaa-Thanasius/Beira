import time
import asyncio
import aiohttp
from typing import Tuple

import textwrap

from bs4 import BeautifulSoup

''''
class WordPress:
    """Get ACI information based on given story and search phrase input."""
    def __init__(self, story: str, search_limit: int = 0):
        self.aci_main_site = "https://aci100.com/"
        self.aci_story_toc = "https://aci100.com/all{}chapters/"
        self.search_limit = search_limit
'''


class ACI100PagesSearch:
    """
    Get ACI100 WordPress pages information based on given story and search phrase input.
    Note: Not generalized for other WordPress sites, since ACI100 doesn't use posts or entry titles for their works.
    """

    def __init__(self, project_name, *, session: aiohttp.ClientSession, aci100_story: str, search_words: list[str],
                 urls_file: str = "chapter_links.txt",
                 results_file: str = "search_output.txt"):

        print("Instantiating ACI100PagesSearch object...")

        self.project_name = project_name
        self.web_session = session
        self.aci100_story = [f"https://aci100.com/{aci100_story}year1",
                             f"https://aci100.com/{aci100_story}year2",
                             f"https://aci100.com/all{aci100_story}chapters"]
        self.search_words = search_words
        self.urls_file = urls_file
        self.results_file = results_file
        self.processed_urls = []

    async def get_toc(self, urls: list[str], file: str) -> None:
        """
        Get links from a WordPress.com table of contents page and write them to a file.
        """

        print("-- get_toc(): Entered")
        start_time = time.perf_counter()

        all_urls = []

        for url in urls:
            print(f"-- {url}\n")
            async with self.web_session.get(url) as response:
                text = await response.text()
                soup = BeautifulSoup(text, "html.parser")
                toc = soup.find("div", class_="entry-content")

                example_link = "https://aci100.com/pop##/"

                all_urls += [f'{link.get("href")}\n' for link in toc.find_all("a")
                             if link.get("href") is not None
                             and len(link.get("href")) <= len(example_link)]

        print(all_urls)
        with open(file, "w") as f:
            f.writelines(all_urls)

        end_time = time.perf_counter()
        print(f"-- get_toc(): Exited! Time taken - {end_time - start_time:.7f}")

    async def get_aci_page_info(self, url: str) -> Tuple[str, BeautifulSoup | None]:
        """
        Get the title and content of an ACI100 WP page.
        :param url: String form of the webpage URL to be used for the query.
        :return: Tuple of the page's title and content
        """

        print("------ get_aci_page_info(): Entered")
        print(f"------ {url}\n")
        start_time = time.perf_counter()

        async with self.web_session.get(url) as resp:
            # Get and parse chapter content
            text = await resp.text()
            soup = BeautifulSoup(text, "html.parser")
            content = soup.find("div", class_="entry-content")

            potential_titles = content.find_all("h3", class_="wp-block-heading")
            if len(potential_titles) > 0:
                title = "\n".join(p_title.text for p_title in potential_titles)
            else:
                return "Blank", content

            end_time = time.perf_counter()
            print(f"------ get_aci_page_info(): Exited! Time taken - {end_time - start_time:.7f}")

            return title, content

    def check_for_words(self, url: str, chapter: BeautifulSoup, title: str) -> Tuple[list[str], str] | None:
        """
        Check a soup object for presence of any words/phrases from a global list, and return them.
        :param url: String form of the webpage URL that will be marked as seen if any words are
        found.
        :param chapter: BeautifulSoup object with a chapter's paragraphs to search.
        :param title: Name of the chapter.
        :return: Tuple of the list of words found and the string representing that find for
        later file writing.
        """

        print("------ check_for_words(): Entered")
        start_time = time.perf_counter()

        presence = ""
        found_words = []
        if self.search_words is None:
            print("check_for_words(): No search terms, stopping here.")
            return

        for word in self.search_words:
            if word.lower() in chapter.text.lower():
                print(f"PAGE HAS \"{word}\"!\n")
                if url not in self.processed_urls:
                    self.processed_urls.append(url)
                    presence += f"+++++++++{title}+++++++++\n"
                    presence += f"{url}\n\n"
                    print(f"+++++++++{title}+++++++++\n")
                found_words.append(word)
            else:
                print(f"Page missing \"{word}\".\n")

        end_time = time.perf_counter()
        print(f"------ check_for_words(): Exited! Time taken - {end_time - start_time:.7f}")

        return found_words, presence

    async def find_keywords(self, url: str) -> str:
        """
        Finds all paragraphs containing certain keywords on a WordPress.com webpage's content
        section and write them to a file.
        :param url: String form of the webpage URL to be used for the query.
        :return: The paragraphs of text with and related to the searched keywords.
        """

        print("---- find_keywords(): Entered")
        print(f"---- {url}\n")
        start_time = time.perf_counter()

        result = ""  # string to be returned
        # Get post information
        title, chapter = await self.get_aci_page_info(url)
        if title == "Blank":
            return f"Nothing ======= {url}\n"
        # Check if any keywords are in the chapter
        found_words, presence = self.check_for_words(url, chapter, title)
        result += presence
        # If there are keywords present, find the paragraphs containing them and the
        # ones surrounding them for context.
        if found_words:
            result += f"Keywords: {found_words}.\n"
            result += "\n"
            print(f"Keywords: {found_words}.\n")
            # Check all paragraphs
            for para in chapter.find_all("p"):
                old_current_p = ""
                for f_word in found_words:
                    if f_word in para.text:
                        current_p = "Current: " + textwrap.fill(para.text) + "\n\n"
                        # If the paragraph has already been encountered, skip it.
                        if old_current_p == current_p:
                            continue
                        old_current_p = current_p
                        prev_p = f"Previous: {textwrap.fill(para.previous_sibling.previous_sibling.text)}\n\n"
                        next_p = f"Next: {textwrap.fill(para.next_sibling.next_sibling.text)}\n\n"

                        result += "---Section Begin---\n"
                        result += prev_p + current_p + next_p
                        result += "---Section End---\n\n"
                        print(result)
        print("Nothing")

        end_time = time.perf_counter()
        print(f"---- find_keywords(): Exited! Time taken - {end_time - start_time:.7f}")

        return result

    async def start_search(self) -> None:
        """
        Runs a group of asynchronous scraping tasks, collects the results, and writes them
        to a file.
        """

        print("start_search(): Entered")
        start_time = time.perf_counter()

        # Get links to scrape from a .txt file
        # for link in self.aci100_story:
        #     await self.get_toc(link, self.urls_file)

        await self.get_toc(self.aci100_story, self.urls_file)

        with open(self.urls_file, "r", encoding="utf-8") as file_c:
            lines = file_c.read().splitlines()

        tasks = []
        for line in lines:
            tasks.append(asyncio.create_task(self.find_keywords(line)))
            await asyncio.sleep(0.25)
        results = await asyncio.gather(*tasks)

        # Put scraping results in a .txt file
        with open(self.results_file, "w", encoding="utf-8") as file_s:
            file_s.writelines(results)

        end_time = time.perf_counter()
        print(f"start_search(): Exited! Time taken - {end_time - start_time:.7f}")


async def main():
    print("main(): Entered")
    async with aiohttp.ClientSession() as session:
        pop_search = ACI100PagesSearch("ACI100 PoP Black Library Mentions",
                                       session=session,
                                       aci100_story="pop",
                                       search_words=["the black"],
                                       urls_file="chapter_links.txt",
                                       results_file="search_output.txt")
        await pop_search.start_search()
    await asyncio.sleep(0.25)

if __name__ == "__main__":
    print("Program started.")
    asyncio.run(main())
