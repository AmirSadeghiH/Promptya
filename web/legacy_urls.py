"""Unprefixed aliases for every page route, kept for backward compatibility.

The bilingual SEO work made ``/en/…`` and ``/fa/…`` the canonical addresses.
Redirecting the old unprefixed URLs there would have been the tidier move, and
it was rejected on purpose:

* every shared ``promptya.com/post/12/`` link, bookmark and search result would
  have to survive a redirect;
* the PWA ``start_url`` and the service worker's ``/offline/`` precache entry are
  unprefixed, and the installed-app experience should not depend on a redirect;
* the mobile API client and the theme/language cookies already key off the plain
  paths.

So the unprefixed URLs keep returning 200 and simply canonicalise to the reader's
language version. Search engines consolidate on the canonical, users see no
redirect, and the sitemap only ever advertises the prefixed form.

This module exists as a separate URLconf with **no** ``app_name`` so the shared
``web`` namespace keeps resolving against the language-aware resolver in
``core/urls.py``.  A second ``web``-namespaced include would have overwritten it
and quietly sent every ``{% url %}`` back to the unprefixed path.
"""

from web.urls import urlpatterns

#: Same objects, mounted at the unprefixed path.  Deliberately not a copy: adding
#: a route to ``web.urls`` must not be possible to forget here.
urlpatterns = urlpatterns
