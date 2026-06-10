# Card Shop

## Backend (Python / FastAPI)

**Models & Database**

1. How does the system track whether a card has been sold in the database?
2. How are user API keys stored and managed?
3. How does the system track the status of a processing batch, and what states can it be in?
4. How is the card catalog mirrored in the application, and what structured data fields does it store?
5. How does the application handle database schema migrations at startup?
6. How is pagination standardized across API responses?
7. How is the SQLite database configured and where is it stored by default?

**Pricing & Price Sources**

8. How does the system aggregate prices from multiple sources to suggest a card price?
9. How does the application authenticate with the eBay API and manage token caching?
10. How are TCGPlayer Infinite prices fetched and parsed?
11. How does the system match a card to a product when looking up prices, and what fallback strategies does it use?
12. How are historical card prices retrieved from the pricing database?
13. How are eBay sold prices persisted, and how are duplicates handled?
14. What card sub-types are recognized in the pricing system?
15. How is eBay API rate limiting enforced?
16. How does the application connect to the external card database microservice?

**OCR & LLM**

17. How does the system instruct the LLM to extract card information from images?
18. How does the card scanning pipeline detect and correct the orientation of uploaded images?
19. How does the system run OCR and vision models concurrently during card scanning?
20. What image preprocessing steps are applied before sending images to the LLM?
21. How does the system handle LLM responses that aren't properly formatted JSON?
22. How does the system decide which LLM model to use, and how does it detect vision-capable models?
23. How does batch card extraction work — are images processed in parallel or one at a time?

**Matching & Processing**

24. How are card names normalized by stripping variant suffixes like "VMAX" or "ex"?
25. How does fuzzy name matching work, and what similarity threshold is considered a match?
26. How does the system automatically determine which image in a pair is the card front vs. back?
27. How does the system combine vision and OCR results to identify a card?
28. How are card processing tasks run in the background, and how are race conditions prevented?
29. How does the system prevent concurrent writes to the same batch during processing?
30. How does the system determine whether OCR results represent a card front versus a back?

**API Endpoints**

31. How does the batch upload endpoint differ from single card upload in terms of processing?
32. How does the API convert matched batch results into inventory records while avoiding duplicates?
33. How does selling a card work when only part of the quantity is being sold?
34. How does the eBay File Exchange CSV export work, and what category is assumed for Pokemon cards?
35. How can a user rotate a card image after it has been uploaded?
36. How are storage location statistics calculated and exposed via the API?
37. How does the password reset flow work, and how long are reset tokens valid?
38. How does the main backend proxy requests to the OCR microservice?

**Config & Infrastructure**

39. How is the PostgreSQL pricing database connection configured, including connection pooling?
40. What cleanup happens when the FastAPI application shuts down?
41. How are static files and uploaded images served by the application?
42. What file formats are accepted for card image uploads?
43. How are card condition abbreviations mapped to their full display names?
44. What thumbnail sizes are generated at startup, and how does the thumbnail generation work?
45. How is the database session provided to FastAPI route handlers?

**Storage & Utilities**

46. How are storage locations and SKUs generated for inventory items?
47. How does the system find the next available storage location for a new card?
48. How are card image thumbnails generated, and what are the maximum dimensions?
49. How does the Redis cache connection handle reconnection when a health check fails?
50. How are card records converted to API responses, including date formatting?

---

## Frontend (React / TypeScript)

51. How is authentication state managed and persisted across browser sessions?
52. How does the API client handle expired sessions and automatically redirect to login?
53. How does the bulk upload page manage its complex state across all the processing stages?
54. How does the card search hook avoid excessive API calls while the user is typing?
55. How does the edit modal search for cards in the database with debounced input?
56. What price sources are displayed to the user in the pricing panel, and how are they presented?
57. How does the frontend serialize card image pairs for the draft save API?
58. How does the frontend handle HEIC image files from iOS devices?
59. How are browser-local storage keys organized and managed across the application?
60. How does the inventory grid layout adapt between desktop and mobile views?
61. What navigation structure does the sidebar provide, and how are routes organized?
62. How does the application protect routes that require authentication?
63. How does the frontend normalize price data that may come with inconsistent field names?
64. How does the draft panel organize in-progress card submissions?
65. What visual status indicators does the card pair row display during processing?
66. How do toast notifications work, and how long do they remain visible?
67. How is the React Query client configured in terms of data freshness and caching?
68. What default values does the card form provide for condition and quantity fields?
69. How does the pick list page support different viewing modes for the user?
70. How does the card image component handle different sizes and loading errors?

---

# Card Collection

**Backend Routes & Controllers**

1. How does the API handle batch updates to card conditions?
2. How does the collection value history endpoint work, and what data does it return?
3. How many grading-related endpoints are there, and what operations do they cover?
4. How does the repricing endpoint work for updating all card prices at once?
5. How does the upload detection endpoint identify cards from images?
6. What does the admin sync endpoint trigger when called?
7. How is the health check endpoint structured in the application?
8. How does the conditions lookup endpoint work — does it use a separate controller or inline logic?
9. How does the API handle cancellation of grading jobs?
10. How are application settings read and updated through the API?

**Backend Models & Database**

11. How many tables does the database schema define, and what are they?
12. How is the Collection model structured, and what convenience methods does it provide?
13. How are grading results stored and deduplicated in the database?
14. How does the inventory import handle items that already exist?
15. How does the card search build dynamic queries based on different filter criteria?
16. How is the dual-database architecture set up to connect to both local and pricing databases?
17. How do condition multipliers work, and what value is assigned to heavily played cards?
18. How does the Set model keep track of its card count?
19. How are key-value application settings stored and updated in the database?
20. How does the database handle batch removal of cards from a list?

**Backend Services**

21. How does fuzzy card name matching work using Levenshtein distance?
22. How does the system detect and filter out OCR hallucinations in card names?
23. How does the collection pricing service compute total value without making extra database round-trips?
24. How does the price lookup service efficiently fetch latest prices instead of using expensive joins?
25. How does the system calculate whether getting a card graded is financially worthwhile?
26. What edge cases does card number normalization handle in the grading pipeline?
27. How do grading jobs handle retries and what is the backoff strategy?
28. How does the OCR service communicate with the underlying vision model?
29. How does the import service auto-detect whether a pasted list is in a specific format?
30. How does the TCGCSV data service know which API to fetch from?

**Backend Utilities**

31. How does the text parser recognize and extract card information from free-form input?
32. How does the parser registry discover and register available parsers automatically?
33. What columns are included when exporting cards to CSV?
34. How does the inventory service module organize and expose its underlying services?

**Frontend Pages & Components**

35. How is the search page routed and what can users do from it?
36. How does the grading page manage analysis state and present results?
37. What does the picture detector page do and how is it accessed?
38. How does the lists page switch between its different sub-views?
39. How are price history charts rendered, and what time range options does the user have?
40. How does the collection value chart fetch and display historical portfolio data?
41. How does the inline confirmation component replace native browser dialogs?
42. How does dynamic text scaling work in the fluid text component?
43. What detailed analysis data is shown when expanding a grading result row?
44. What card list formats can be imported through the import modal?
45. Does the upload modal support automatic front/back card detection?
46. How is the searchable dropdown component reused across the application?

**Frontend State & API**

47. How does the API service layer handle response wrapping — where does the actual payload live?
48. How does the list data hook support URL-based navigation and filtering?
49. How does the sort state hook render visual indicators for current sort direction?
50. How does the price formatting utility handle null or missing values?

---

# Infrastructure

**Database Schema**

1. How many tables does the main database schema create, and what are they?
2. What columns form the unique constraint that prevents duplicate price records?
3. How are eBay prices stored, and what structured data columns do they include?
4. How does the cards table represent variant information for different card printings?
5. What composite indexes exist to speed up product lookups by card?
6. How many indexes does the schema define in total to optimize query performance?
7. How does the groups table prevent duplicate set entries?
8. What unique constraints ensure product data integrity beyond the primary identifier?
9. How are card categories stored, and which category ID represents Pokemon?
10. How are multi-value fields like card types and Pokedex numbers stored in the database?

**Data Sync Scripts**

11. What are the three main phases of the daily data update process?
12. How does the group update script fetch and store set information from the external API?
13. How does the price update script assign dates to newly fetched records?
14. What three phases does the metadata repair script go through to fix corrupted card data?
15. How does the TCGDex loader support both full reloads and incremental updates?
16. How does the product linking script match cards to their corresponding products?
17. How many new sets does the loader process per run to avoid overwhelming the system?
18. How does the historical price loader download and process archive files?
19. How far back does the archive sync script check for missing price data?
20. How does the image sync script extract card identifiers from filenames?

**Parallel Loaders**

21. What Python concurrency mechanism does the parallel archive processor use?
22. How does the parallel historical loader cap its worker count, and why?
23. What batch size does the fast historical loader use for efficient bulk inserts?
24. How was Docker-based parallel execution set up before it was abandoned?

**Worker & Scheduler**

25. What services make up the infrastructure stack and how are they orchestrated?
26. At what time of day does the scheduler trigger the daily update?
27. What Python version does the worker container run, and how is it built?
28. How does the scheduler's main loop determine when to run scheduled tasks?
29. What restart behavior is configured for infrastructure containers?
30. How is the database health check configured for the PostgreSQL container?

**Utility Functions**

31. What does the default TCGCSV category ID resolve to?
32. How does the batch insert helper handle conflicts when data already exists?
33. What is the default base URL for the TCGDex API?
34. How does the directory creation utility ensure parent paths exist?

**Gluetun / eBay Scraper**

35. How many filter keywords are used to exclude non-card listings from eBay results?
36. How does the scraper handle cards that are commonly confused across different sets?
37. How does the system identify whether an eBay listing title describes a graded card?
38. How does the search query builder progress from specific to general queries?
39. How does the statistics computation handle outliers when calculating raw card values?
40. What scraping framework does the eBay spider use, and how does it avoid detection?
41. How does the multi-grade scraper optimize when higher grades return no results?
42. How does the spider rate-limit its requests to avoid being blocked?
43. What browser automation does the legacy eBay scraper use?
44. How does the browser manager handle the lifecycle of headless browser instances?

**Scraper API**

45. What endpoints does the scraper API expose for triggering scrapes?
46. What information is required in a scrape request payload?
47. What port does the scraper API listen on?
48. What does the bulk test harness output when validating scraper results?

**Configuration**

49. What are the default database credentials and connection parameters?
50. How is the Gluetun VPN container configured, and which provider does it connect to?

---

# Scripts

> *Note: The scripts project is smaller, so these questions also cover cross-project migration concepts and the broader ecosystem wiring.*

**Migration Scripts**

1. What are the three phases of the SQLite to PostgreSQL migration?
2. How does the set migration match migrated sets to existing groups in the target database?
3. What placeholder identifier is used for new groups that don't have an external ID yet?
4. How does the card migration batch inserts for performance?
5. Which JSON fields need special parsing during the card migration, and why?
6. How does the migration verification step confirm that data was transferred correctly?
7. How does the standalone card migration script differ from the three-phase migration?
8. What table structure does the standalone card migration create in PostgreSQL?
9. What indexes does the standalone card migration create to optimize lookups?
10. How many columns does the migrated card table have in the PostgreSQL version?

**Cross-Project Connections**

11. How does the Card Shop backend connect to the infrastructure pricing database?
12. How does the Card Collection backend establish its connection to the shared pricing database?
13. What Docker network allows the Card Shop backend to reach the infrastructure PostgreSQL?
14. How does the Card Collection docker-compose reference the shared pricing network?
15. How does the Card Shop backend trigger eBay scraping through the Gluetun stack?
16. How does the Card Collection grading service call the eBay scraper?
17. How does the Card Shop backend reach the OCR microservice within Docker?
18. How does the Card Collection backend connect to the OCR service?
19. How does the Card Shop backend use the external card database microservice?
20. How does the Card Collection backend sync TCGCSV pricing data?

**Card Shop → Infrastructure Data Flow**

21. How does the Card Shop look up products by matching card data against the infrastructure database?
22. How does the Card Shop query the infrastructure products table with joins to get pricing data?
23. How does the Card Shop persist eBay pricing data back to the infrastructure database?
24. How does the Card Shop determine whether cached TCGPlayer prices are stale and need refreshing?
25. How does the Card Shop use the infrastructure groups table during price lookups?

**Card Collection → Infrastructure Data Flow**

26. How does the Card Collection search the infrastructure products table when looking up a card?
27. How does the Card Collection rank and select the best matching product when multiple candidates exist?
28. How does the Card Collection efficiently batch-fetch the latest prices from the infrastructure database?
29. What does "preferred sub-type" mean when enriching card data from the pricing database?
30. How do the two price-fetching methods in Card Collection differ in scope — one for specific cards vs. all cards?

**Shared Patterns**

31. Both projects normalize card names — how do their approaches differ?
32. How do the two projects' condition grading systems compare in terms of multipliers and mapping?
33. Both projects connect to the same PostgreSQL instance — how do their connection configurations compare?
34. How is Redis used differently across the two projects?
35. Both projects integrate with an OCR service — are they using the same service or different ones?

**Docker & Deployment**

36. What services does the Card Shop's compose file define?
37. How are uploaded files volume-mounted in the Card Shop's Docker setup?
38. Is the Card Shop backend set up for hot reload or does it require rebuilding on code changes?
39. Does the Card Shop frontend support live code updates in Docker or does it need a rebuild?
40. What external network does the Card Collection's compose file join?
41. How is the nginx proxy configured for the Card Collection frontend, particularly around API timeouts?
42. What does the Card Collection's development make target do?
43. What does the infrastructure's make target for running the worker actually execute?
44. Are Docker restart policies consistent across all projects?
45. Which services across all projects have health checks defined?

**Environment & Configuration**

46. How many environment template files exist across all four projects?
47. How is the JWT signing key managed — is it fixed or configurable via environment variables?
48. How is the Redis connection URL configured, and what is the default?
49. How is the local LLM studio URL configured, and can it be overridden per user?
50. How long are JWT tokens valid by default in the Card Shop?
