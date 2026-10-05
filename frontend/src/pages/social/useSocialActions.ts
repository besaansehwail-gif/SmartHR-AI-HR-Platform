import { useCallback, useState } from 'react';

import { SmartHRApi } from '../../services/api';
import { useToast } from '../../components/ui/Toast';
import { useT } from '../../i18n';

/**
 * Connecting with somebody, and opening a conversation with them.
 *
 * Three pages offer the same four actions - the feed's right rail, People, and
 * a profile - so they are written once here rather than three times with three
 * slightly different toasts. Every handler re-reads the affected screen through
 * the `onChanged` callback the page supplies: the server is the authority on
 * whether a request went through, so nothing is patched into local state on
 * the assumption that it did.
 */
export const useSocialActions = (onChanged: () => void | Promise<void>) => {
  const { t } = useT();
  const { showToast } = useToast();
  const [busy, setBusy] = useState(false);

  const run = useCallback(
    async (action: () => Promise<unknown>, title: string, message?: string) => {
      setBusy(true);
      try {
        await action();
        showToast(title, { message, type: 'success' });
        await onChanged();
      } catch (error) {
        // The server's own sentence, not a generic one: it says *why*, and
        // the codes behind these (409 on a duplicate, 404 on somebody else's
        // row) already read correctly to a person.
        showToast(t('social.connect.failed'), {
          message: error instanceof Error ? error.message : undefined,
          type: 'error',
        });
      } finally {
        setBusy(false);
      }
    },
    [onChanged, showToast, t]
  );

  const connect = useCallback(
    (userId: number, name?: string) =>
      run(
        () => SmartHRApi.requestSocialConnection(userId),
        t('social.connect.requestSent'),
        name ? t('social.connect.requestSentBody', { name }) : undefined
      ),
    [run, t]
  );

  const accept = useCallback(
    (connectionId: number) =>
      run(
        () => SmartHRApi.acceptSocialConnection(connectionId),
        t('social.connect.accepted')
      ),
    [run, t]
  );

  const reject = useCallback(
    (connectionId: number) =>
      run(
        () => SmartHRApi.rejectSocialConnection(connectionId),
        t('social.connect.rejected')
      ),
    [run, t]
  );

  const disconnect = useCallback(
    (connectionId: number, name: string) => {
      // Disconnecting throws away an accepted connection, so it is confirmed.
      // Sending a request is not - it is reversible by the same button.
      if (!window.confirm(t('social.connect.disconnectConfirm', { name }))) return;

      return run(
        () => SmartHRApi.removeSocialConnection(connectionId),
        t('social.connect.removed')
      );
    },
    [run, t]
  );

  return { busy, connect, accept, reject, disconnect };
};

/**
 * Open a thread with a colleague and hand the id back.
 *
 * `POST /social/conversations` is idempotent for a pair, so pressing Message
 * from three different screens lands in the same conversation rather than
 * creating three.
 */
export const useOpenConversation = (
  onOpened: (conversationId: number) => void
) => {
  const { t } = useT();
  const { showToast } = useToast();

  return useCallback(
    async (userId: number) => {
      try {
        const conversation = await SmartHRApi.startSocialConversation(userId);
        onOpened(conversation.id);
      } catch (error) {
        showToast(t('social.connect.failed'), {
          message: error instanceof Error ? error.message : undefined,
          type: 'error',
        });
      }
    },
    [onOpened, showToast, t]
  );
};
