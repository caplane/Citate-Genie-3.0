"""
citeflex/config.py

Configuration, constants, and shared settings.

Version History:
    2025-12-10: Added OPENAI_API_KEY and ANTHROPIC_API_KEY with .lstrip('=') fix
    2025-12-07: Added SERPAPI_KEY for Google Scholar integration
    2025-12-05: Added version tracking, fixed get_gov_agency to check specific domains first
"""

import os
from typing import Dict

# =============================================================================
# API KEYS (from environment)
# =============================================================================

# AI/LLM API Keys (strip whitespace and leading '=' from copy-paste artifacts)
_raw_openai = os.environ.get('OPENAI_API_KEY', '')
_raw_anthropic = os.environ.get('ANTHROPIC_API_KEY', '')
OPENAI_API_KEY = _raw_openai.strip().lstrip('=')
ANTHROPIC_API_KEY = _raw_anthropic.strip().lstrip('=')

# Debug: Log if we stripped anything
if _raw_openai.startswith('='):
    print(f"[Config] WARNING: Stripped '=' from OPENAI_API_KEY. Raw started with: {_raw_openai[:10]}...")
if _raw_openai and not _raw_openai.startswith('='):
    print(f"[Config] OPENAI_API_KEY loaded OK (no '=' prefix). Starts with: {OPENAI_API_KEY[:10]}...")
if not _raw_openai:
    print("[Config] WARNING: OPENAI_API_KEY not set in environment")

# Other API Keys
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
COURTLISTENER_API_KEY = os.environ.get('CL_API_KEY', '')
PUBMED_API_KEY = os.environ.get('PUBMED_API_KEY', '')
SEMANTIC_SCHOLAR_API_KEY = os.environ.get('SEMANTIC_SCHOLAR_API_KEY', '')
GOOGLE_CSE_API_KEY = os.environ.get('GOOGLE_CSE_API_KEY', '')
GOOGLE_CSE_ID = os.environ.get('GOOGLE_CSE_ID', '')
SERPAPI_KEY = os.environ.get('SERPAPI_KEY', '')
BRAVE_API_KEY = os.environ.get('BRAVE_API_KEY', '')  # For fast URL citation lookup

# =============================================================================
# HTTP SETTINGS
# =============================================================================

DEFAULT_TIMEOUT = 10  # seconds
DEFAULT_HEADERS = {
    'User-Agent': 'CiteFlex/2.0 (mailto:user@example.com)',
    'Accept': 'application/json'
}

# =============================================================================
# GEMINI SETTINGS
# =============================================================================

GEMINI_MODEL = 'gemini-2.0-flash'

# =============================================================================
# NEWSPAPER DOMAIN MAPPING
# =============================================================================

NEWSPAPER_DOMAINS: Dict[str, str] = {
    # ==========================================================================
    # UNITED STATES
    # ==========================================================================
    'nytimes.com': 'The New York Times',
    'washingtonpost.com': 'The Washington Post',
    'wsj.com': 'The Wall Street Journal',
    'theatlantic.com': 'The Atlantic',
    'newyorker.com': 'The New Yorker',
    'slate.com': 'Slate',
    'politico.com': 'Politico',
    'reuters.com': 'Reuters',
    'apnews.com': 'Associated Press',
    'bloomberg.com': 'Bloomberg',
    'forbes.com': 'Forbes',
    'time.com': 'Time',
    'newsweek.com': 'Newsweek',
    'vox.com': 'Vox',
    'vice.com': 'Vice',
    'wired.com': 'Wired',
    'cnn.com': 'CNN',
    'foxnews.com': 'Fox News',
    'nbcnews.com': 'NBC News',
    'cbsnews.com': 'CBS News',
    'abcnews.go.com': 'ABC News',
    'latimes.com': 'Los Angeles Times',
    'chicagotribune.com': 'Chicago Tribune',
    'bostonglobe.com': 'The Boston Globe',
    'usatoday.com': 'USA Today',
    'nypost.com': 'New York Post',
    'sfchronicle.com': 'San Francisco Chronicle',
    'seattletimes.com': 'The Seattle Times',
    'denverpost.com': 'The Denver Post',
    'dallasnews.com': 'The Dallas Morning News',
    'houstonchronicle.com': 'Houston Chronicle',
    'miamiherald.com': 'Miami Herald',
    'philly.com': 'The Philadelphia Inquirer',
    'inquirer.com': 'The Philadelphia Inquirer',
    'startribune.com': 'Star Tribune',
    'azcentral.com': 'The Arizona Republic',
    'oregonlive.com': 'The Oregonian',
    'mercurynews.com': 'The Mercury News',
    'thedailybeast.com': 'The Daily Beast',
    'huffpost.com': 'HuffPost',
    'buzzfeednews.com': 'BuzzFeed News',
    'thehill.com': 'The Hill',
    'axios.com': 'Axios',
    'motherjones.com': 'Mother Jones',
    'thenation.com': 'The Nation',
    'nationalreview.com': 'National Review',
    'theweek.com': 'The Week',
    'foreignaffairs.com': 'Foreign Affairs',
    'foreignpolicy.com': 'Foreign Policy',
    'harpers.org': 'Harper\'s Magazine',
    'theintercept.com': 'The Intercept',
    'propublica.org': 'ProPublica',
    
    # ==========================================================================
    # UNITED KINGDOM
    # ==========================================================================
    'theguardian.com': 'The Guardian',
    'bbc.com': 'BBC News',
    'bbc.co.uk': 'BBC News',
    'telegraph.co.uk': 'The Telegraph',
    'independent.co.uk': 'The Independent',
    'dailymail.co.uk': 'Daily Mail',
    'mirror.co.uk': 'Daily Mirror',
    'thesun.co.uk': 'The Sun',
    'ft.com': 'Financial Times',
    'economist.com': 'The Economist',
    'thetimes.co.uk': 'The Times',
    'standard.co.uk': 'Evening Standard',
    'express.co.uk': 'Daily Express',
    'metro.co.uk': 'Metro',
    'newstatesman.com': 'New Statesman',
    'spectator.co.uk': 'The Spectator',
    'theweek.co.uk': 'The Week UK',
    'inews.co.uk': 'i News',
    'cityam.com': 'City A.M.',
    'scotsman.com': 'The Scotsman',
    'heraldscotland.com': 'The Herald',
    'walesonline.co.uk': 'Wales Online',
    'belfasttelegraph.co.uk': 'Belfast Telegraph',
    'irishtimes.com': 'The Irish Times',
    
    # ==========================================================================
    # CANADA
    # ==========================================================================
    'theglobeandmail.com': 'The Globe and Mail',
    'thestar.com': 'Toronto Star',
    'nationalpost.com': 'National Post',
    'cbc.ca': 'CBC News',
    'globalnews.ca': 'Global News',
    'ctv.ca': 'CTV News',
    'ctvnews.ca': 'CTV News',
    'montrealgazette.com': 'Montreal Gazette',
    'ottawacitizen.com': 'Ottawa Citizen',
    'calgaryherald.com': 'Calgary Herald',
    'edmontonjournal.com': 'Edmonton Journal',
    'vancouversun.com': 'Vancouver Sun',
    'theprovince.com': 'The Province',
    'winnipegfreepress.com': 'Winnipeg Free Press',
    'thechronicleherald.ca': 'The Chronicle Herald',
    'ledevoir.com': 'Le Devoir',
    'lapresse.ca': 'La Presse',
    'journaldemontreal.com': 'Le Journal de Montréal',
    'macleans.ca': 'Maclean\'s',
    'thewalrus.ca': 'The Walrus',
    'canadaland.com': 'Canadaland',
    
    # ==========================================================================
    # AUSTRALIA
    # ==========================================================================
    'smh.com.au': 'The Sydney Morning Herald',
    'theaustralian.com.au': 'The Australian',
    'abc.net.au': 'ABC News',
    'theguardian.com/australia-news': 'The Guardian Australia',
    'news.com.au': 'News.com.au',
    'heraldsun.com.au': 'Herald Sun',
    'dailytelegraph.com.au': 'The Daily Telegraph',
    'theage.com.au': 'The Age',
    'couriermail.com.au': 'The Courier-Mail',
    'watoday.com.au': 'WAtoday',
    'perthnow.com.au': 'PerthNow',
    'adelaidenow.com.au': 'Adelaide Now',
    'brisbanetimes.com.au': 'Brisbane Times',
    'canberratimes.com.au': 'The Canberra Times',
    'sbs.com.au': 'SBS News',
    'crikey.com.au': 'Crikey',
    'theconversation.com': 'The Conversation',
    'themonthly.com.au': 'The Monthly',
    'quarterlyessay.com.au': 'Quarterly Essay',
    'afr.com': 'Australian Financial Review',
    
    # ==========================================================================
    # NEW ZEALAND
    # ==========================================================================
    'nzherald.co.nz': 'The New Zealand Herald',
    'stuff.co.nz': 'Stuff',
    'rnz.co.nz': 'RNZ',
    'newshub.co.nz': 'Newshub',
    'odt.co.nz': 'Otago Daily Times',
    'thepress.co.nz': 'The Press',
    'nzme.co.nz': 'NZME',
    'newsroom.co.nz': 'Newsroom',
    'interest.co.nz': 'Interest.co.nz',
    'nbr.co.nz': 'National Business Review',
    'listener.co.nz': 'New Zealand Listener',
    'noted.co.nz': 'Noted',
    'thespinoff.co.nz': 'The Spinoff',
    
    # ==========================================================================
    # IRELAND
    # ==========================================================================
    'irishtimes.com': 'The Irish Times',
    'independent.ie': 'Irish Independent',
    'irishexaminer.com': 'Irish Examiner',
    'rte.ie': 'RTÉ News',
    'thejournal.ie': 'The Journal',
    'breakingnews.ie': 'BreakingNews.ie',
    'businesspost.ie': 'Business Post',
    'irishmirror.ie': 'Irish Mirror',
    'herald.ie': 'Herald',
    'dublinlive.ie': 'Dublin Live',
    
    # ==========================================================================
    # EUROPEAN UNION / EUROPE
    # ==========================================================================
    'politico.eu': 'Politico Europe',
    'euronews.com': 'Euronews',
    'dw.com': 'Deutsche Welle',
    'france24.com': 'France 24',
    'lemonde.fr': 'Le Monde',
    'lefigaro.fr': 'Le Figaro',
    'liberation.fr': 'Libération',
    'spiegel.de': 'Der Spiegel',
    'zeit.de': 'Die Zeit',
    'faz.net': 'Frankfurter Allgemeine',
    'sueddeutsche.de': 'Süddeutsche Zeitung',
    'corriere.it': 'Corriere della Sera',
    'repubblica.it': 'La Repubblica',
    'elpais.com': 'El País',
    'elmundo.es': 'El Mundo',
    'publico.pt': 'Público',
    'nrc.nl': 'NRC Handelsblad',
    'volkskrant.nl': 'de Volkskrant',
    'svd.se': 'Svenska Dagbladet',
    'dn.se': 'Dagens Nyheter',
    
    # ==========================================================================
    # INTERNATIONAL / WIRE SERVICES
    # ==========================================================================
    'aljazeera.com': 'Al Jazeera',
    'scmp.com': 'South China Morning Post',
    'japantimes.co.jp': 'The Japan Times',
    'straitstimes.com': 'The Straits Times',
    'hindustantimes.com': 'Hindustan Times',
    'timesofindia.indiatimes.com': 'The Times of India',
    'afp.com': 'Agence France-Presse',
}

# =============================================================================
# GOVERNMENT AGENCY MAPPING
# =============================================================================

GOV_AGENCY_MAP: Dict[str, str] = {
    # ==========================================================================
    # UNITED STATES (.gov)
    # ==========================================================================
    'fda.gov': 'U.S. Food and Drug Administration',
    'cdc.gov': 'Centers for Disease Control and Prevention',
    'nih.gov': 'National Institutes of Health',
    'epa.gov': 'Environmental Protection Agency',
    'regulations.gov': 'U.S. Government',
    'doe.gov': 'U.S. Department of Energy',
    'energy.gov': 'U.S. Department of Energy',
    'directives.doe.gov': 'U.S. Department of Energy',
    'whitehouse.gov': 'The White House',
    'congress.gov': 'U.S. Congress',
    'supremecourt.gov': 'Supreme Court of the United States',
    'justice.gov': 'U.S. Department of Justice',
    'state.gov': 'U.S. Department of State',
    'treasury.gov': 'U.S. Department of the Treasury',
    'defense.gov': 'U.S. Department of Defense',
    'ed.gov': 'U.S. Department of Education',
    'hhs.gov': 'U.S. Department of Health and Human Services',
    'dhs.gov': 'U.S. Department of Homeland Security',
    'usda.gov': 'U.S. Department of Agriculture',
    'commerce.gov': 'U.S. Department of Commerce',
    'labor.gov': 'U.S. Department of Labor',
    'transportation.gov': 'U.S. Department of Transportation',
    'va.gov': 'U.S. Department of Veterans Affairs',
    'archives.gov': 'National Archives',
    'loc.gov': 'Library of Congress',
    'census.gov': 'U.S. Census Bureau',
    'bls.gov': 'Bureau of Labor Statistics',
    'sec.gov': 'Securities and Exchange Commission',
    'ftc.gov': 'Federal Trade Commission',
    'fcc.gov': 'Federal Communications Commission',
    'federalreserve.gov': 'Federal Reserve',
    'cms.gov': 'Centers for Medicare & Medicaid Services',
    'samhsa.gov': 'Substance Abuse and Mental Health Services Administration',
    'nimh.nih.gov': 'National Institute of Mental Health',
    'ncbi.nlm.nih.gov': 'National Center for Biotechnology Information',
    'pubmed.gov': 'National Library of Medicine',
    'uscourts.gov': 'U.S. Courts',
    'gao.gov': 'Government Accountability Office',
    'cbo.gov': 'Congressional Budget Office',
    'gpo.gov': 'Government Publishing Office',
    'opm.gov': 'Office of Personnel Management',
    'ssa.gov': 'Social Security Administration',
    'fema.gov': 'Federal Emergency Management Agency',
    'nasa.gov': 'NASA',
    'nsf.gov': 'National Science Foundation',
    'usaid.gov': 'U.S. Agency for International Development',
    'fbi.gov': 'Federal Bureau of Investigation',
    'atf.gov': 'Bureau of Alcohol, Tobacco, Firearms and Explosives',
    'dea.gov': 'Drug Enforcement Administration',
    'ice.gov': 'U.S. Immigration and Customs Enforcement',
    'cbp.gov': 'U.S. Customs and Border Protection',
    'irs.gov': 'Internal Revenue Service',
    'sba.gov': 'Small Business Administration',
    'faa.gov': 'Federal Aviation Administration',
    'nhtsa.gov': 'National Highway Traffic Safety Administration',
    'nist.gov': 'National Institute of Standards and Technology',
    'noaa.gov': 'National Oceanic and Atmospheric Administration',
    'nps.gov': 'National Park Service',
    'usgs.gov': 'U.S. Geological Survey',
    'ferc.gov': 'Federal Energy Regulatory Commission',
    
    # ==========================================================================
    # UNITED KINGDOM (.gov.uk)
    # ==========================================================================
    'gov.uk': 'UK Government',
    'parliament.uk': 'UK Parliament',
    'legislation.gov.uk': 'UK Legislation',
    'nationalarchives.gov.uk': 'The National Archives',
    'ons.gov.uk': 'Office for National Statistics',
    'nhs.uk': 'National Health Service',
    'nice.org.uk': 'National Institute for Health and Care Excellence',
    'bankofengland.co.uk': 'Bank of England',
    'fca.org.uk': 'Financial Conduct Authority',
    'cqc.org.uk': 'Care Quality Commission',
    'ico.org.uk': 'Information Commissioner\'s Office',
    'ofcom.org.uk': 'Ofcom',
    'ofsted.gov.uk': 'Ofsted',
    'judiciary.uk': 'UK Judiciary',
    'supremecourt.uk': 'UK Supreme Court',
    'scotcourts.gov.uk': 'Scottish Courts',
    'gov.scot': 'Scottish Government',
    'gov.wales': 'Welsh Government',
    'northernireland.gov.uk': 'Northern Ireland Government',
    'niassembly.gov.uk': 'Northern Ireland Assembly',
    'senedd.wales': 'Welsh Parliament',
    'scottish.parliament.uk': 'Scottish Parliament',
    'bl.uk': 'British Library',
    'royalsociety.org': 'The Royal Society',
    
    # ==========================================================================
    # CANADA (.gc.ca, .canada.ca)
    # ==========================================================================
    'canada.ca': 'Government of Canada',
    'gc.ca': 'Government of Canada',
    'pm.gc.ca': 'Prime Minister of Canada',
    'parl.ca': 'Parliament of Canada',
    'scc-csc.ca': 'Supreme Court of Canada',
    'justice.gc.ca': 'Department of Justice Canada',
    'laws-lois.justice.gc.ca': 'Justice Laws Website',
    'canada.gc.ca': 'Government of Canada',
    'statcan.gc.ca': 'Statistics Canada',
    'cra-arc.gc.ca': 'Canada Revenue Agency',
    'ircc.gc.ca': 'Immigration, Refugees and Citizenship Canada',
    'cbsa-asfc.gc.ca': 'Canada Border Services Agency',
    'rcmp-grc.gc.ca': 'Royal Canadian Mounted Police',
    'forces.gc.ca': 'Canadian Armed Forces',
    'international.gc.ca': 'Global Affairs Canada',
    'tc.gc.ca': 'Transport Canada',
    'hc-sc.gc.ca': 'Health Canada',
    'canada.ca/en/health-canada': 'Health Canada',
    'cihr-irsc.gc.ca': 'Canadian Institutes of Health Research',
    'nrc-cnrc.gc.ca': 'National Research Council Canada',
    'nserc-crsng.gc.ca': 'Natural Sciences and Engineering Research Council',
    'sshrc-crsh.gc.ca': 'Social Sciences and Humanities Research Council',
    'bac-lac.gc.ca': 'Library and Archives Canada',
    'cbc.radio-canada.ca': 'CBC/Radio-Canada',
    'bankofcanada.ca': 'Bank of Canada',
    'osfi-bsif.gc.ca': 'Office of the Superintendent of Financial Institutions',
    'elections.ca': 'Elections Canada',
    'oag-bvg.gc.ca': 'Office of the Auditor General',
    'pco-bcp.gc.ca': 'Privy Council Office',
    'fin.gc.ca': 'Department of Finance Canada',
    'ic.gc.ca': 'Innovation, Science and Economic Development Canada',
    'agr.gc.ca': 'Agriculture and Agri-Food Canada',
    'nrcan.gc.ca': 'Natural Resources Canada',
    'ec.gc.ca': 'Environment and Climate Change Canada',
    'dfo-mpo.gc.ca': 'Fisheries and Oceans Canada',
    'pc.gc.ca': 'Parks Canada',
    'veterans.gc.ca': 'Veterans Affairs Canada',
    'crtc.gc.ca': 'Canadian Radio-television and Telecommunications Commission',
    
    # Provincial governments
    'ontario.ca': 'Government of Ontario',
    'quebec.ca': 'Government of Quebec',
    'gov.bc.ca': 'Government of British Columbia',
    'alberta.ca': 'Government of Alberta',
    'gov.mb.ca': 'Government of Manitoba',
    'gov.sk.ca': 'Government of Saskatchewan',
    'gov.ns.ca': 'Government of Nova Scotia',
    'gnb.ca': 'Government of New Brunswick',
    'gov.nl.ca': 'Government of Newfoundland and Labrador',
    'gov.pe.ca': 'Government of Prince Edward Island',
    'gov.nt.ca': 'Government of Northwest Territories',
    'gov.nu.ca': 'Government of Nunavut',
    'gov.yk.ca': 'Government of Yukon',
    
    # ==========================================================================
    # AUSTRALIA (.gov.au)
    # ==========================================================================
    'gov.au': 'Australian Government',
    'australia.gov.au': 'Australian Government',
    'pm.gov.au': 'Prime Minister of Australia',
    'aph.gov.au': 'Parliament of Australia',
    'hcourt.gov.au': 'High Court of Australia',
    'fedcourt.gov.au': 'Federal Court of Australia',
    'legislation.gov.au': 'Federal Register of Legislation',
    'abs.gov.au': 'Australian Bureau of Statistics',
    'ato.gov.au': 'Australian Taxation Office',
    'homeaffairs.gov.au': 'Department of Home Affairs',
    'border.gov.au': 'Australian Border Force',
    'afp.gov.au': 'Australian Federal Police',
    'defence.gov.au': 'Department of Defence',
    'dfat.gov.au': 'Department of Foreign Affairs and Trade',
    'ag.gov.au': 'Attorney-General\'s Department',
    'health.gov.au': 'Department of Health',
    'tga.gov.au': 'Therapeutic Goods Administration',
    'nhmrc.gov.au': 'National Health and Medical Research Council',
    'csiro.au': 'CSIRO',
    'arc.gov.au': 'Australian Research Council',
    'education.gov.au': 'Department of Education',
    'infrastructure.gov.au': 'Department of Infrastructure',
    'treasury.gov.au': 'Treasury',
    'rba.gov.au': 'Reserve Bank of Australia',
    'apra.gov.au': 'Australian Prudential Regulation Authority',
    'asic.gov.au': 'Australian Securities and Investments Commission',
    'accc.gov.au': 'Australian Competition and Consumer Commission',
    'oaic.gov.au': 'Office of the Australian Information Commissioner',
    'aec.gov.au': 'Australian Electoral Commission',
    'anao.gov.au': 'Australian National Audit Office',
    'nla.gov.au': 'National Library of Australia',
    'naa.gov.au': 'National Archives of Australia',
    'bom.gov.au': 'Bureau of Meteorology',
    'environment.gov.au': 'Department of Climate Change, Energy, the Environment and Water',
    'agriculture.gov.au': 'Department of Agriculture',
    'servicesaustralia.gov.au': 'Services Australia',
    
    # State/Territory governments
    'nsw.gov.au': 'NSW Government',
    'vic.gov.au': 'Victorian Government',
    'qld.gov.au': 'Queensland Government',
    'wa.gov.au': 'Government of Western Australia',
    'sa.gov.au': 'Government of South Australia',
    'tas.gov.au': 'Tasmanian Government',
    'nt.gov.au': 'Northern Territory Government',
    'act.gov.au': 'ACT Government',
    
    # ==========================================================================
    # NEW ZEALAND (.govt.nz)
    # ==========================================================================
    'govt.nz': 'New Zealand Government',
    'beehive.govt.nz': 'New Zealand Government (Beehive)',
    'dpmc.govt.nz': 'Department of the Prime Minister and Cabinet',
    'parliament.nz': 'New Zealand Parliament',
    'courtsofnz.govt.nz': 'Courts of New Zealand',
    'legislation.govt.nz': 'New Zealand Legislation',
    'stats.govt.nz': 'Stats NZ',
    'ird.govt.nz': 'Inland Revenue',
    'immigration.govt.nz': 'Immigration New Zealand',
    'customs.govt.nz': 'New Zealand Customs Service',
    'police.govt.nz': 'New Zealand Police',
    'nzdf.mil.nz': 'New Zealand Defence Force',
    'mfat.govt.nz': 'Ministry of Foreign Affairs and Trade',
    'justice.govt.nz': 'Ministry of Justice',
    'health.govt.nz': 'Ministry of Health',
    'medsafe.govt.nz': 'Medsafe',
    'hrc.govt.nz': 'Health Research Council',
    'education.govt.nz': 'Ministry of Education',
    'mbie.govt.nz': 'Ministry of Business, Innovation and Employment',
    'treasury.govt.nz': 'The Treasury',
    'rbnz.govt.nz': 'Reserve Bank of New Zealand',
    'fma.govt.nz': 'Financial Markets Authority',
    'comcom.govt.nz': 'Commerce Commission',
    'privacy.org.nz': 'Office of the Privacy Commissioner',
    'elections.nz': 'Electoral Commission',
    'oag.parliament.nz': 'Office of the Auditor-General',
    'natlib.govt.nz': 'National Library of New Zealand',
    'archives.govt.nz': 'Archives New Zealand',
    'doc.govt.nz': 'Department of Conservation',
    'mfe.govt.nz': 'Ministry for the Environment',
    'mpi.govt.nz': 'Ministry for Primary Industries',
    'transport.govt.nz': 'Ministry of Transport',
    'nzta.govt.nz': 'Waka Kotahi NZ Transport Agency',
    'msd.govt.nz': 'Ministry of Social Development',
    'tewhatuora.govt.nz': 'Te Whatu Ora - Health New Zealand',
    
    # ==========================================================================
    # IRELAND (.gov.ie)
    # ==========================================================================
    'gov.ie': 'Government of Ireland',
    'oireachtas.ie': 'Houses of the Oireachtas',
    'courts.ie': 'Courts Service of Ireland',
    'supremecourt.ie': 'Supreme Court of Ireland',
    'irishstatutebook.ie': 'Irish Statute Book',
    'cso.ie': 'Central Statistics Office',
    'revenue.ie': 'Revenue Commissioners',
    'citizensinformation.ie': 'Citizens Information',
    'gardai.ie': 'An Garda Síochána',
    'military.ie': 'Defence Forces Ireland',
    'dfa.ie': 'Department of Foreign Affairs',
    'justice.ie': 'Department of Justice',
    'hse.ie': 'Health Service Executive',
    'hiqa.ie': 'Health Information and Quality Authority',
    'hrb.ie': 'Health Research Board',
    'education.ie': 'Department of Education',
    'hea.ie': 'Higher Education Authority',
    'sfi.ie': 'Science Foundation Ireland',
    'irc.ie': 'Irish Research Council',
    'finance.gov.ie': 'Department of Finance',
    'centralbank.ie': 'Central Bank of Ireland',
    'dataprotection.ie': 'Data Protection Commission',
    'rte.ie': 'RTÉ',
    'nli.ie': 'National Library of Ireland',
    'nationalarchives.ie': 'National Archives of Ireland',
    'epa.ie': 'Environmental Protection Agency',
    'seai.ie': 'Sustainable Energy Authority of Ireland',
    
    # ==========================================================================
    # EUROPEAN UNION (.europa.eu)
    # ==========================================================================
    'europa.eu': 'European Union',
    'ec.europa.eu': 'European Commission',
    'europarl.europa.eu': 'European Parliament',
    'consilium.europa.eu': 'Council of the European Union',
    'curia.europa.eu': 'Court of Justice of the European Union',
    'eur-lex.europa.eu': 'EUR-Lex',
    'eurostat.ec.europa.eu': 'Eurostat',
    'ecb.europa.eu': 'European Central Bank',
    'eba.europa.eu': 'European Banking Authority',
    'esma.europa.eu': 'European Securities and Markets Authority',
    'ema.europa.eu': 'European Medicines Agency',
    'efsa.europa.eu': 'European Food Safety Authority',
    'eea.europa.eu': 'European Environment Agency',
    'frontex.europa.eu': 'Frontex',
    'europol.europa.eu': 'Europol',
    'eurojust.europa.eu': 'Eurojust',
    'erc.europa.eu': 'European Research Council',
    'cordis.europa.eu': 'CORDIS',
    'edps.europa.eu': 'European Data Protection Supervisor',
    'ombudsman.europa.eu': 'European Ombudsman',
    'cor.europa.eu': 'European Committee of the Regions',
    'eesc.europa.eu': 'European Economic and Social Committee',
    'who.int': 'World Health Organization',
    'un.org': 'United Nations',
    'oecd.org': 'OECD',
    'imf.org': 'International Monetary Fund',
    'worldbank.org': 'World Bank',
    'wto.org': 'World Trade Organization',
}

# =============================================================================
# PUBLISHER PLACE MAPPING (for books)
# =============================================================================

PUBLISHER_PLACE_MAP: Dict[str, str] = {
    'Harvard University Press': 'Cambridge, MA',
    'MIT Press': 'Cambridge, MA',
    'Yale University Press': 'New Haven',
    'Princeton University Press': 'Princeton',
    'Stanford University Press': 'Stanford',
    'University of California Press': 'Berkeley',
    'University of Chicago Press': 'Chicago',
    'Columbia University Press': 'New York',
    'Oxford University Press': 'Oxford',
    'Cambridge University Press': 'Cambridge',
    'Penguin': 'New York',
    'Random House': 'New York',
    'HarperCollins': 'New York',
    'Simon & Schuster': 'New York',
    'Farrar, Straus and Giroux': 'New York',
    'W. W. Norton': 'New York',
    'Knopf': 'New York',
    'Routledge': 'London',
    'Bloomsbury': 'London',
    'Sage Publications': 'Thousand Oaks',
    'Wiley': 'Hoboken',
    'Springer': 'New York',
    'Elsevier': 'Amsterdam',
    'Taylor & Francis': 'London',
    'Palgrave Macmillan': 'London',
    'Duke University Press': 'Durham',
    'Johns Hopkins University Press': 'Baltimore',
    'University of Pennsylvania Press': 'Philadelphia',
    'Cornell University Press': 'Ithaca',
    'University of Michigan Press': 'Ann Arbor',
    'University of North Carolina Press': 'Chapel Hill',
    'University of Texas Press': 'Austin',
    'University of Wisconsin Press': 'Madison',
    'Indiana University Press': 'Bloomington',
    'Northwestern University Press': 'Evanston',
    'Basic Books': 'New York',
    'Free Press': 'New York',
    'Vintage': 'New York',
    'Anchor Books': 'New York',
}

# =============================================================================
# LEGAL DOMAINS
# =============================================================================

LEGAL_DOMAINS = [
    # ==========================================================================
    # UNITED STATES
    # ==========================================================================
    'courtlistener.com',
    'oyez.org',
    'case.law',
    'justia.com',
    'supremecourt.gov',
    'law.cornell.edu',
    'findlaw.com',
    'heinonline.org',
    'westlaw.com',
    'lexisnexis.com',
    'uscourts.gov',
    'pacer.gov',
    'law.justia.com',
    'casetext.com',
    'fastcase.com',
    'scholar.google.com/scholar_case',
    'leagle.com',
    'casemine.com',
    
    # ==========================================================================
    # UNITED KINGDOM
    # ==========================================================================
    'bailii.org',
    'legislation.gov.uk',
    'supremecourt.uk',
    'judiciary.uk',
    'nationalarchives.gov.uk/doc',
    'caselaw.nationalarchives.gov.uk',
    'lawreports.co.uk',
    'iclr.co.uk',
    'westlaw.co.uk',
    'lexisnexis.co.uk',
    'practicallaw.co.uk',
    'lawtel.com',
    
    # ==========================================================================
    # CANADA
    # ==========================================================================
    'canlii.org',
    'laws-lois.justice.gc.ca',
    'scc-csc.ca',
    'fct-cf.gc.ca',
    'fca-caf.gc.ca',
    'canlii.ca',
    'lexum.com',
    'westlawnext.canada.com',
    'quicklaw.com',
    
    # ==========================================================================
    # AUSTRALIA
    # ==========================================================================
    'austlii.edu.au',
    'legislation.gov.au',
    'hcourt.gov.au',
    'fedcourt.gov.au',
    'fwc.gov.au',
    'aiatsis.gov.au',
    'nswcaselaw.nsw.gov.au',
    'sclqld.org.au',
    'lawreform.vic.gov.au',
    'westlaw.com.au',
    'lexisnexis.com.au',
    'jade.io',
    
    # ==========================================================================
    # NEW ZEALAND
    # ==========================================================================
    'nzlii.org',
    'legislation.govt.nz',
    'courtsofnz.govt.nz',
    'westlaw.co.nz',
    'lexisnexis.co.nz',
    
    # ==========================================================================
    # IRELAND
    # ==========================================================================
    'bailii.org/ie',
    'irishstatutebook.ie',
    'courts.ie',
    'supremecourt.ie',
    'lawreform.ie',
    'irlii.org',
    'westlaw.ie',
    
    # ==========================================================================
    # EUROPEAN UNION / INTERNATIONAL
    # ==========================================================================
    'eur-lex.europa.eu',
    'curia.europa.eu',
    'echr.coe.int',
    'hudoc.echr.coe.int',
    'icc-cpi.int',
    'icj-cij.org',
    'legal.un.org',
    'wipo.int',
    'worldlii.org',
    'commonlii.org',
]

# =============================================================================
# ACADEMIC PUBLISHER DOMAINS (for Google CSE parsing)
# =============================================================================

ACADEMIC_DOMAINS = {
    'jstor.org': 'JSTOR',
    'academic.oup.com': 'Oxford Academic',
    'oup.com': 'Oxford University Press',
    'cambridge.org': 'Cambridge University Press',
    'tandfonline.com': 'Taylor & Francis',
    'springer.com': 'Springer',
    'link.springer.com': 'Springer',
    'wiley.com': 'Wiley',
    'onlinelibrary.wiley.com': 'Wiley',
    'sagepub.com': 'SAGE',
    'projectmuse.org': 'Project MUSE',
    'sciencedirect.com': 'ScienceDirect',
    'pubmed.ncbi.nlm.nih.gov': 'PubMed',
    'scholar.google.com': 'Google Scholar',
    'hathitrust.org': 'HathiTrust',
    'archive.org': 'Internet Archive',
    'worldcat.org': 'WorldCat',
}

# =============================================================================
# MEDICAL TERMS (for detection)
# =============================================================================

MEDICAL_TERMS = [
    'clinical', 'patient', 'treatment', 'therapy', 'diagnosis',
    'disease', 'syndrome', 'pharmaceutical', 'drug', 'medicine',
    'medical', 'hospital', 'physician', 'pubmed', 'ncbi',
    'randomized', 'placebo', 'trial', 'efficacy', 'dosage',
    'pathology', 'prognosis', 'etiology', 'symptom', 'chronic',
    'acute', 'disorder', 'condition', 'intervention', 'outcome',
]

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def resolve_publisher_place(publisher: str, current_place: str = "") -> str:
    """Look up publication place for known publishers."""
    if current_place:
        return current_place
    if not publisher:
        return ''
    for pub_name, pub_place in PUBLISHER_PLACE_MAP.items():
        if pub_name.lower() in publisher.lower():
            return pub_place
    return ''


def get_newspaper_name(domain: str) -> str:
    """Get newspaper name from domain."""
    domain = domain.lower().replace('www.', '')
    for key, name in NEWSPAPER_DOMAINS.items():
        if key in domain:
            return name
    return "Unknown Publication"


def get_gov_agency(domain: str) -> str:
    """
    Get government agency name from domain.
    
    Updated: 2025-12-08 - Added international government support
    Updated: 2025-12-05 - Check longer/more specific domains first
    """
    domain = domain.lower().replace('www.', '')
    
    # Sort keys by length descending so more specific domains match first
    # e.g., 'nimh.nih.gov' should match before 'nih.gov'
    sorted_keys = sorted(GOV_AGENCY_MAP.keys(), key=len, reverse=True)
    
    for key in sorted_keys:
        if key in domain:
            return GOV_AGENCY_MAP[key]
    
    # Fallback labels based on domain pattern
    if '.gov.uk' in domain or domain.endswith('gov.uk'):
        return "UK Government"
    if '.gc.ca' in domain or '.canada.ca' in domain:
        return "Government of Canada"
    if '.gov.au' in domain:
        return "Australian Government"
    if '.govt.nz' in domain:
        return "New Zealand Government"
    if '.gov.ie' in domain:
        return "Government of Ireland"
    if '.europa.eu' in domain:
        return "European Union"
    if '.gov.scot' in domain:
        return "Scottish Government"
    if '.gov.wales' in domain:
        return "Welsh Government"
    if '.gov' in domain:
        return "U.S. Government"
    
    return "Government"
