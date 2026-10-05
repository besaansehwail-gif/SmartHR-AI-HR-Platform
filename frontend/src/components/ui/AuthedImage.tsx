import React, { useEffect, useState } from 'react';

import { fetchMediaObjectUrl } from '../../services/api';

/**
 * An image whose URL needs the session token.
 *
 * `GET /social/media/{name}` is guarded by `require_staff`, like every other
 * route in the Social Hub - an Applicant must not be able to fetch a
 * colleague's photograph by guessing a URL. But a plain `<img src>` sends no
 * Authorization header, so the browser's request arrives unauthenticated and
 * the server correctly answers **401**. Measured, not assumed: the route
 * returns 401 to a request with no header, and `uploads/social/` is not a
 * static mount.
 *
 * So the bytes are fetched the way every other request is fetched - through
 * `apiFetch`'s token - and handed to the tag as an object URL. The guard is
 * untouched; only the transport changes.
 *
 * The object URL is revoked when the component unmounts or the source
 * changes, so a feed the user scrolls through does not accumulate them.
 */

interface AuthedImageProps {
  /** The API path the server returned, e.g. `/social/media/x.png`. */
  src: string | null | undefined;
  alt: string;
  className?: string;
  /** Rendered while the bytes are loading, and if they cannot be loaded. */
  fallback?: React.ReactNode;
}

export const AuthedImage: React.FC<AuthedImageProps> = ({
  src,
  alt,
  className,
  fallback = null,
}) => {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    let created: string | null = null;

    setObjectUrl(null);
    setFailed(false);

    if (!src) return undefined;

    void (async () => {
      try {
        const url = await fetchMediaObjectUrl(src);
        if (!live) {
          URL.revokeObjectURL(url);
          return;
        }
        created = url;
        setObjectUrl(url);
      } catch {
        // A missing or refused image is not worth an error banner over a
        // working feed: the caller's fallback renders instead.
        if (live) setFailed(true);
      }
    })();

    return () => {
      live = false;
      if (created) URL.revokeObjectURL(created);
    };
  }, [src]);

  if (!src || failed) return <>{fallback}</>;
  if (!objectUrl) return <>{fallback}</>;

  return (
    <img
      src={objectUrl}
      alt={alt}
      loading="lazy"
      decoding="async"
      className={className}
    />
  );
};
