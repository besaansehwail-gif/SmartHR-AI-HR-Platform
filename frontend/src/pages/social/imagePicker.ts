/**
 * Choosing an image to attach, and refusing it early when it will not do.
 *
 * The real validation is the server's: `app/social_storage.py` detects the type
 * from the file's **signature**, not its name, so a renamed executable is
 * rejected there whatever this file thinks. What happens here is a courtesy -
 * a 6 MB photograph should be refused before it is uploaded rather than after,
 * and the `accept` attribute keeps the picker itself tidy.
 *
 * The limits match the server's exactly so the two cannot disagree: 4 MB, and
 * PNG / JPEG / GIF / WebP.
 */

/** Matches `MAX_IMAGE_BYTES` in app/social_storage.py. */
export const MAX_IMAGE_BYTES = 4 * 1024 * 1024;

/** Matches the signatures app/social_storage.py detects. */
export const ACCEPTED_IMAGE_TYPES = 'image/png,image/jpeg,image/gif,image/webp';

const ACCEPTED_MIME = new Set([
  'image/png',
  'image/jpeg',
  'image/jpg',
  'image/gif',
  'image/webp',
]);

/** Suffix of the dictionary key describing why a file was refused. */
export type ImageRejection = 'imageTooLarge' | 'imageType';

export interface PickImageOptions {
  onPicked: (file: File) => void;
  onRejected?: (reason: ImageRejection) => void;
}

/**
 * Open the file picker and hand back one acceptable image.
 *
 * Built imperatively rather than as a hidden `<input>` in every component that
 * needs one: three screens attach images and none of them wants to own an
 * input element, a ref and a change handler to do it.
 */
export const pickImage = ({ onPicked, onRejected }: PickImageOptions): void => {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = ACCEPTED_IMAGE_TYPES;

  input.addEventListener('change', () => {
    const file = input.files?.[0];
    if (!file) return;

    if (!ACCEPTED_MIME.has(file.type)) {
      onRejected?.('imageType');
      return;
    }

    if (file.size > MAX_IMAGE_BYTES) {
      onRejected?.('imageTooLarge');
      return;
    }

    onPicked(file);
  });

  input.click();
};
