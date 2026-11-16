"""Shared Streamlit fragment: reference controls never rerun the scientific viewer."""
from __future__ import annotations

import streamlit as st

from . import references as ref
from .reference_view import viewer_html
from .targets import validate_coordinates, validate_fov_deg


@st.cache_data(ttl=12 * 3600, max_entries=32, show_spinner=False)
def cached_gaia(ra: float, dec: float, fov: float) -> dict:
    return ref.fetch_gaia(ra, dec, fov)


@st.fragment
def render(ra: float, dec: float, fov: float, *, key: str) -> None:
    ra, dec = validate_coordinates(ra, dec)
    fov = validate_fov_deg(fov)
    with st.expander("Astronomical references · Gaia / WISE"):
        st.caption(f"Same region: ICRS RA {ra:.6f}°, Dec {dec:+.6f}° · diameter {60*fov:g}′. "
                   "The centre and the field are changed in the explorer.")
        if not st.toggle("Open reference viewer", key=f"{key}_open"):
            return
        st.info("Independent reference: Gaia is a catalogue; AllWISE is an infrared image from another mission "
                "(WISE era 2010–2011, combined product; local epoch not verified). W1 ≈ 3.4 µm / W2 ≈ 4.6 µm; "
                "WISE resolution ≈ 6″, different from the resolution and bands of SPHEREx. A visual difference "
                "does not prove variability. No images are subtracted and no sources are associated automatically.")
        use_gaia = st.checkbox("Query Gaia DR3 in this field", key=f"{key}_query")
        result, error = None, None
        if use_gaia:
            if st.button("Retry / refresh Gaia", key=f"{key}_retry"):
                cached_gaia.clear(ra, dec, fov)
            try:
                with st.spinner("Querying Gaia DR3 (maximum 500 sources)…", show_time=True):
                    result = cached_gaia(ra, dec, fov)
            except ref.ReferenceError as err:
                error = str(err)
                st.warning(error)
        epoch = st.number_input("Epoch of the computed position (Julian year TCB)", min_value=2000.0,
                                max_value=2050.0, value=2026.0, step=0.1, key=f"{key}_epoch")
        st.caption("Cyan circles: Gaia DR3 J2016.0. Optional amber crosses: approximate computed position "
                   "with RA, Dec, ref_epoch, pmra (= μα cos δ) and pmdec; no parallax, radial velocity, "
                   "perspective acceleration or propagated uncertainty. It is not a SPHEREx detection. "
                   "Sources without proper motion: catalogue position only.")
        if result:
            st.caption(f"{len(result['sources'])} sources · query {result['retrieved_utc']} · "
                       "circular selection at J2016.0, ordered by G magnitude; it does not include external sources "
                       "that may enter the field at another epoch. Absence from Gaia does not rule out an infrared source.")
            if result["truncated"]:
                st.warning("Field truncated to 500 sources by G magnitude. It is not a complete census.")
            with st.expander("Gaia provenance and parameter table"):
                st.markdown(f"[ESA Gaia DR3]({ref.GAIA_DOC}) · `{ref.GAIA_TABLE}`. "
                            "RA/Dec in degrees; errors/parallax in mas; pm in mas/yr; radial velocity in km/s; G in mag; RUWE dimensionless.")
                st.dataframe(result["sources"], hide_index=True)
                st.code(result["query"], language="sql")
                st.caption(f"SHA-256 of the CSV response: {result['sha256']}")
        st.iframe(viewer_html(ra, dec, fov, result, epoch, error), height=760)
        st.markdown(f"AllWISE/IPAC: [W1]({ref.WISE_URLS['W1']}/properties) · "
                    f"[W2]({ref.WISE_URLS['W2']}/properties) · "
                    "[AllWISE supplement](https://wise2.ipac.caltech.edu/docs/release/allwise/expsup/) · "
                    "[Aladin Lite 3.8.1 / CDS](https://github.com/cds-astro/aladin-lite/releases/tag/v3.8.1). "
                    "HiPS JPEG for visual context, no photometric use; it has no single epoch per source.")
