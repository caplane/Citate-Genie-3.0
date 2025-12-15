"""
gov_ngo_domains.py

Government and NGO organization names for citation formatting.
Maps domain names to citation-correct full names.

When a URL from one of these domains is processed, the organization name
should be used verbatim as the author - NOT parsed as a human name.

Usage:
    from gov_ngo_domains import get_org_author
    
    author = get_org_author("cdc.gov")
    # Returns: "Centers for Disease Control and Prevention"

Sources:
    - USA.gov A-Z Agency Index
    - Official organization websites
    - APA/Chicago citation guides

Last updated: 2025-12-15
"""

# =============================================================================
# U.S. CABINET DEPARTMENTS (15)
# =============================================================================

US_CABINET_DEPARTMENTS = {
    # Department of Agriculture
    "usda.gov": "U.S. Department of Agriculture",
    
    # Department of Commerce
    "commerce.gov": "U.S. Department of Commerce",
    "doc.gov": "U.S. Department of Commerce",
    
    # Department of Defense
    "defense.gov": "U.S. Department of Defense",
    "dod.gov": "U.S. Department of Defense",
    
    # Department of Education
    "ed.gov": "U.S. Department of Education",
    
    # Department of Energy
    "energy.gov": "U.S. Department of Energy",
    "doe.gov": "U.S. Department of Energy",
    
    # Department of Health and Human Services
    "hhs.gov": "U.S. Department of Health and Human Services",
    
    # Department of Homeland Security
    "dhs.gov": "U.S. Department of Homeland Security",
    
    # Department of Housing and Urban Development
    "hud.gov": "U.S. Department of Housing and Urban Development",
    
    # Department of the Interior
    "doi.gov": "U.S. Department of the Interior",
    "interior.gov": "U.S. Department of the Interior",
    
    # Department of Justice
    "justice.gov": "U.S. Department of Justice",
    "doj.gov": "U.S. Department of Justice",
    
    # Department of Labor
    "dol.gov": "U.S. Department of Labor",
    
    # Department of State
    "state.gov": "U.S. Department of State",
    
    # Department of Transportation
    "transportation.gov": "U.S. Department of Transportation",
    "dot.gov": "U.S. Department of Transportation",
    
    # Department of the Treasury
    "treasury.gov": "U.S. Department of the Treasury",
    
    # Department of Veterans Affairs
    "va.gov": "U.S. Department of Veterans Affairs",
}

# =============================================================================
# U.S. MAJOR AGENCIES AND BUREAUS
# =============================================================================

US_AGENCIES = {
    # Health agencies
    "cdc.gov": "Centers for Disease Control and Prevention",
    "fda.gov": "U.S. Food and Drug Administration",
    "nih.gov": "National Institutes of Health",
    "cms.gov": "Centers for Medicare and Medicaid Services",
    "samhsa.gov": "Substance Abuse and Mental Health Services Administration",
    "hrsa.gov": "Health Resources and Services Administration",
    "ahrq.gov": "Agency for Healthcare Research and Quality",
    
    # Science and technology agencies
    "nasa.gov": "National Aeronautics and Space Administration",
    "nsf.gov": "National Science Foundation",
    "noaa.gov": "National Oceanic and Atmospheric Administration",
    "usgs.gov": "U.S. Geological Survey",
    "nist.gov": "National Institute of Standards and Technology",
    
    # Environmental agencies
    "epa.gov": "U.S. Environmental Protection Agency",
    
    # Financial and economic agencies
    "sec.gov": "U.S. Securities and Exchange Commission",
    "ftc.gov": "Federal Trade Commission",
    "fdic.gov": "Federal Deposit Insurance Corporation",
    "federalreserve.gov": "Board of Governors of the Federal Reserve System",
    "consumerfinance.gov": "Consumer Financial Protection Bureau",
    "sba.gov": "U.S. Small Business Administration",
    
    # Law enforcement and intelligence
    "fbi.gov": "Federal Bureau of Investigation",
    "cia.gov": "Central Intelligence Agency",
    "atf.gov": "Bureau of Alcohol, Tobacco, Firearms and Explosives",
    "dea.gov": "Drug Enforcement Administration",
    "ice.gov": "U.S. Immigration and Customs Enforcement",
    "cbp.gov": "U.S. Customs and Border Protection",
    "secretservice.gov": "U.S. Secret Service",
    "usmarshals.gov": "U.S. Marshals Service",
    
    # Regulatory agencies
    "fcc.gov": "Federal Communications Commission",
    "faa.gov": "Federal Aviation Administration",
    "nhtsa.gov": "National Highway Traffic Safety Administration",
    "osha.gov": "Occupational Safety and Health Administration",
    "cpsc.gov": "U.S. Consumer Product Safety Commission",
    "nrc.gov": "U.S. Nuclear Regulatory Commission",
    "ferc.gov": "Federal Energy Regulatory Commission",
    
    # Statistical agencies
    "census.gov": "U.S. Census Bureau",
    "bls.gov": "U.S. Bureau of Labor Statistics",
    "bea.gov": "U.S. Bureau of Economic Analysis",
    "eia.gov": "U.S. Energy Information Administration",
    
    # Tax and revenue
    "irs.gov": "Internal Revenue Service",
    
    # Social services
    "ssa.gov": "Social Security Administration",
    "acf.hhs.gov": "Administration for Children and Families",
    
    # Congressional agencies
    "gao.gov": "U.S. Government Accountability Office",
    "cbo.gov": "Congressional Budget Office",
    "loc.gov": "Library of Congress",
    "gpo.gov": "U.S. Government Publishing Office",
    
    # Independent agencies
    "usps.com": "U.S. Postal Service",
    "amtrak.com": "National Railroad Passenger Corporation",
    "smithsonian.edu": "Smithsonian Institution",
    "archives.gov": "National Archives and Records Administration",
    "peace corps.gov": "Peace Corps",
    "fema.gov": "Federal Emergency Management Agency",
    
    # Military branches
    "army.mil": "U.S. Army",
    "navy.mil": "U.S. Navy",
    "af.mil": "U.S. Air Force",
    "marines.mil": "U.S. Marine Corps",
    "uscg.mil": "U.S. Coast Guard",
    "spaceforce.mil": "U.S. Space Force",
    
    # Courts
    "supremecourt.gov": "Supreme Court of the United States",
    "uscourts.gov": "Administrative Office of the U.S. Courts",
}

# =============================================================================
# UNITED NATIONS SYSTEM
# =============================================================================

UN_SYSTEM = {
    # Core UN
    "un.org": "United Nations",
    
    # UN specialized agencies
    "who.int": "World Health Organization",
    "unesco.org": "United Nations Educational, Scientific and Cultural Organization",
    "ilo.org": "International Labour Organization",
    "fao.org": "Food and Agriculture Organization of the United Nations",
    "imf.org": "International Monetary Fund",
    "worldbank.org": "World Bank",
    "wto.org": "World Trade Organization",
    "wipo.int": "World Intellectual Property Organization",
    "itu.int": "International Telecommunication Union",
    "icao.int": "International Civil Aviation Organization",
    "imo.org": "International Maritime Organization",
    "unido.org": "United Nations Industrial Development Organization",
    "unwto.org": "World Tourism Organization",
    "upu.int": "Universal Postal Union",
    "wmo.int": "World Meteorological Organization",
    "ifad.org": "International Fund for Agricultural Development",
    
    # UN programmes and funds
    "unicef.org": "United Nations Children's Fund",
    "undp.org": "United Nations Development Programme",
    "unhcr.org": "United Nations High Commissioner for Refugees",
    "unep.org": "United Nations Environment Programme",
    "unfpa.org": "United Nations Population Fund",
    "wfp.org": "World Food Programme",
    "unaids.org": "Joint United Nations Programme on HIV/AIDS",
    
    # UN related organizations
    "iaea.org": "International Atomic Energy Agency",
    "opcw.org": "Organisation for the Prohibition of Chemical Weapons",
    "ctbto.org": "Comprehensive Nuclear-Test-Ban Treaty Organization",
    
    # Regional UN bodies
    "unece.org": "United Nations Economic Commission for Europe",
    "eclac.org": "Economic Commission for Latin America and the Caribbean",
    "unescap.org": "United Nations Economic and Social Commission for Asia and the Pacific",
    "uneca.org": "United Nations Economic Commission for Africa",
    "escwa.un.org": "United Nations Economic and Social Commission for Western Asia",
}

# =============================================================================
# INTERNATIONAL FINANCIAL INSTITUTIONS
# =============================================================================

INTERNATIONAL_FINANCIAL = {
    # World Bank Group
    "worldbank.org": "World Bank",
    "ifc.org": "International Finance Corporation",
    
    # Regional development banks
    "adb.org": "Asian Development Bank",
    "afdb.org": "African Development Bank",
    "ebrd.com": "European Bank for Reconstruction and Development",
    "iadb.org": "Inter-American Development Bank",
    "aiib.org": "Asian Infrastructure Investment Bank",
    
    # Other international economic organizations
    "oecd.org": "Organisation for Economic Co-operation and Development",
    "bis.org": "Bank for International Settlements",
}

# =============================================================================
# EUROPEAN UNION
# =============================================================================

EU_INSTITUTIONS = {
    # Core EU institutions
    "europa.eu": "European Union",
    "ec.europa.eu": "European Commission",
    "europarl.europa.eu": "European Parliament",
    "consilium.europa.eu": "Council of the European Union",
    "curia.europa.eu": "Court of Justice of the European Union",
    "eca.europa.eu": "European Court of Auditors",
    
    # EU agencies
    "ecb.europa.eu": "European Central Bank",
    "ema.europa.eu": "European Medicines Agency",
    "efsa.europa.eu": "European Food Safety Authority",
    "echa.europa.eu": "European Chemicals Agency",
    "eea.europa.eu": "European Environment Agency",
    "frontex.europa.eu": "European Border and Coast Guard Agency",
    "europol.europa.eu": "European Union Agency for Law Enforcement Cooperation",
    "eurojust.europa.eu": "European Union Agency for Criminal Justice Cooperation",
    "ecdc.europa.eu": "European Centre for Disease Prevention and Control",
}

# =============================================================================
# UNITED KINGDOM
# =============================================================================

UK_GOVERNMENT = {
    # Core UK government
    "gov.uk": "United Kingdom Government",
    
    # Major UK departments and agencies
    "nhs.uk": "National Health Service",
    "ons.gov.uk": "Office for National Statistics",
    "bankofengland.co.uk": "Bank of England",
    "nice.org.uk": "National Institute for Health and Care Excellence",
    "gov.scot": "Scottish Government",
    "gov.wales": "Welsh Government",
    "northernireland.gov.uk": "Northern Ireland Executive",
}

# =============================================================================
# CANADA
# =============================================================================

CANADA_GOVERNMENT = {
    "canada.ca": "Government of Canada",
    "statcan.gc.ca": "Statistics Canada",
    "canada.gc.ca": "Government of Canada",
    "cihr-irsc.gc.ca": "Canadian Institutes of Health Research",
    "inspection.gc.ca": "Canadian Food Inspection Agency",
    "nrc-cnrc.gc.ca": "National Research Council Canada",
    "crtc.gc.ca": "Canadian Radio-television and Telecommunications Commission",
    "bankofcanada.ca": "Bank of Canada",
}

# =============================================================================
# AUSTRALIA
# =============================================================================

AUSTRALIA_GOVERNMENT = {
    "australia.gov.au": "Australian Government",
    "abs.gov.au": "Australian Bureau of Statistics",
    "csiro.au": "Commonwealth Scientific and Industrial Research Organisation",
    "health.gov.au": "Australian Government Department of Health",
    "tga.gov.au": "Therapeutic Goods Administration",
    "rba.gov.au": "Reserve Bank of Australia",
    "aihw.gov.au": "Australian Institute of Health and Welfare",
    "nhmrc.gov.au": "National Health and Medical Research Council",
}

# =============================================================================
# U.S. STATES (Top 10 + Honorable Mentions)
# =============================================================================

US_STATES = {
    # Top 10 Most-Cited States
    
    # 1. California - Most innovative state, policy trendsetter
    "ca.gov": "State of California",
    "california.gov": "State of California",
    
    # 2. New York - Second in R&D, major policy influence
    "ny.gov": "State of New York",
    "nyc.gov": "City of New York",
    
    # 3. Texas - Third in R&D, major policy lab
    "texas.gov": "State of Texas",
    "tx.gov": "State of Texas",
    
    # 4. Florida - Regional leader, third largest state
    "myflorida.com": "State of Florida",
    "florida.gov": "State of Florida",
    "fl.gov": "State of Florida",
    
    # 5. Massachusetts - Healthcare policy pioneer, biotech hub
    "mass.gov": "Commonwealth of Massachusetts",
    "massachusetts.gov": "Commonwealth of Massachusetts",
    
    # 6. Illinois - Regional leader, Chicago influence
    "illinois.gov": "State of Illinois",
    "il.gov": "State of Illinois",
    
    # 7. Colorado - First state for AI regulation, innovation leader
    "colorado.gov": "State of Colorado",
    "co.gov": "State of Colorado",
    
    # 8. Washington - Tech policy leader, environmental policy
    "wa.gov": "State of Washington",
    "washington.gov": "State of Washington",
    
    # 9. Minnesota - Regional leader, policy innovator
    "mn.gov": "State of Minnesota",
    "minnesota.gov": "State of Minnesota",
    
    # 10. North Carolina - Regional leader, emerging policy innovator
    "nc.gov": "State of North Carolina",
    "northcarolina.gov": "State of North Carolina",
    
    # Honorable Mentions
    
    # Pennsylvania
    "pa.gov": "Commonwealth of Pennsylvania",
    "pennsylvania.gov": "Commonwealth of Pennsylvania",
    
    # New Jersey
    "nj.gov": "State of New Jersey",
    "newjersey.gov": "State of New Jersey",
    
    # Ohio
    "ohio.gov": "State of Ohio",
    "oh.gov": "State of Ohio",
    
    # Virginia
    "virginia.gov": "Commonwealth of Virginia",
    # Note: va.gov belongs to U.S. Department of Veterans Affairs (federal)
    
    # Connecticut
    "ct.gov": "State of Connecticut",
    "connecticut.gov": "State of Connecticut",
}

# =============================================================================
# OTHER INTERNATIONAL ORGANIZATIONS
# =============================================================================

OTHER_INTERNATIONAL = {
    # NATO and security
    "nato.int": "North Atlantic Treaty Organization",
    
    # Commonwealth
    "thecommonwealth.org": "Commonwealth of Nations",
    
    # Other major organizations
    "icrc.org": "International Committee of the Red Cross",
    "ifrc.org": "International Federation of Red Cross and Red Crescent Societies",
    "amnesty.org": "Amnesty International",
    "hrw.org": "Human Rights Watch",
    "transparency.org": "Transparency International",
    "greenpeace.org": "Greenpeace International",
    "oxfam.org": "Oxfam International",
    "msf.org": "Médecins Sans Frontières",
    "doctorswithoutborders.org": "Doctors Without Borders",
    
    # Standards organizations
    "iso.org": "International Organization for Standardization",
    "ieee.org": "Institute of Electrical and Electronics Engineers",
    
    # Sports organizations
    "olympic.org": "International Olympic Committee",
    "fifa.com": "Fédération Internationale de Football Association",
}

# =============================================================================
# COMBINED LOOKUP DICTIONARY
# =============================================================================

ORG_DOMAINS = {
    **US_CABINET_DEPARTMENTS,
    **US_AGENCIES,
    **US_STATES,
    **UN_SYSTEM,
    **INTERNATIONAL_FINANCIAL,
    **EU_INSTITUTIONS,
    **UK_GOVERNMENT,
    **CANADA_GOVERNMENT,
    **AUSTRALIA_GOVERNMENT,
    **OTHER_INTERNATIONAL,
}


# =============================================================================
# LOOKUP FUNCTIONS
# =============================================================================

def normalize_domain(url_or_domain: str) -> str:
    """
    Extract and normalize domain from URL or domain string.
    
    Args:
        url_or_domain: Full URL or domain string
        
    Returns:
        Normalized domain (lowercase, no www prefix)
    """
    domain = url_or_domain.lower().strip()
    
    # Remove protocol
    if "://" in domain:
        domain = domain.split("://", 1)[1]
    
    # Remove path
    if "/" in domain:
        domain = domain.split("/", 1)[0]
    
    # Remove www prefix
    if domain.startswith("www."):
        domain = domain[4:]
    
    return domain


def get_org_author(url_or_domain: str) -> str | None:
    """
    Get the official organization name for citation purposes.
    
    Args:
        url_or_domain: Full URL or domain string
        
    Returns:
        Official organization name, or None if not found
        
    Example:
        >>> get_org_author("https://www.cdc.gov/some/page.html")
        "Centers for Disease Control and Prevention"
    """
    domain = normalize_domain(url_or_domain)
    
    # Try exact match first
    if domain in ORG_DOMAINS:
        return ORG_DOMAINS[domain]
    
    # Try matching subdomains (e.g., "cancer.gov" should match if we have it)
    # Also try parent domains (e.g., "sub.cdc.gov" should match "cdc.gov")
    parts = domain.split(".")
    for i in range(len(parts) - 1):
        parent_domain = ".".join(parts[i:])
        if parent_domain in ORG_DOMAINS:
            return ORG_DOMAINS[parent_domain]
    
    return None


def is_org_domain(url_or_domain: str) -> bool:
    """
    Check if a URL/domain belongs to a known organization.
    
    Args:
        url_or_domain: Full URL or domain string
        
    Returns:
        True if the domain is in the organization database
    """
    return get_org_author(url_or_domain) is not None


def is_gov_domain(url_or_domain: str) -> bool:
    """
    Check if a URL/domain is a government domain.
    
    Args:
        url_or_domain: Full URL or domain string
        
    Returns:
        True if the domain ends with .gov, .gov.*, .mil, etc.
    """
    domain = normalize_domain(url_or_domain)
    
    gov_suffixes = [
        ".gov", ".gov.uk", ".gov.au", ".gov.ca",
        ".gc.ca", ".gov.nz", ".gov.ie",
        ".mil", ".edu"
    ]
    
    return any(domain.endswith(suffix) for suffix in gov_suffixes)


# =============================================================================
# STATISTICS
# =============================================================================

def get_stats() -> dict:
    """Return statistics about the organization database."""
    return {
        "total_domains": len(ORG_DOMAINS),
        "us_cabinet": len(US_CABINET_DEPARTMENTS),
        "us_agencies": len(US_AGENCIES),
        "us_states": len(US_STATES),
        "un_system": len(UN_SYSTEM),
        "international_financial": len(INTERNATIONAL_FINANCIAL),
        "eu_institutions": len(EU_INSTITUTIONS),
        "uk_government": len(UK_GOVERNMENT),
        "canada_government": len(CANADA_GOVERNMENT),
        "australia_government": len(AUSTRALIA_GOVERNMENT),
        "other_international": len(OTHER_INTERNATIONAL),
    }


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    # Print statistics
    stats = get_stats()
    print("=== Organization Domains Database ===")
    print(f"Total domains: {stats['total_domains']}")
    print()
    for key, value in stats.items():
        if key != "total_domains":
            print(f"  {key}: {value}")
    
    print("\n=== Test Lookups ===")
    test_urls = [
        "https://www.cdc.gov/some/page.html",
        "https://who.int/publications/report.pdf",
        "https://www.nih.gov/research",
        "https://europa.eu/policy",
        "https://www.gov.uk/guidance",
        "https://unknown-site.com/page",
        "fda.gov",
        "ec.europa.eu",
        # State government tests
        "https://www.ca.gov/departments/",
        "https://www.ny.gov/services",
        "https://www.texas.gov/health",
        "https://www.mass.gov/report",
    ]
    
    for url in test_urls:
        result = get_org_author(url)
        status = result if result else "NOT FOUND"
        print(f"{url[:40]:40} -> {status}")
