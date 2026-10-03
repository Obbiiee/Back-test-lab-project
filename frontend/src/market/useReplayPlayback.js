import { useCallback, useEffect, useState } from 'react';
import { PlaybackScheduler } from './PlaybackScheduler.js';

export default function useReplayPlayback(replay, speed) {
  const [requested, setRequested] = useState(false);
  const [scheduler] = useState(() => new PlaybackScheduler());
  const playing = requested && replay.active && !replay.loading && !replay.atEnd;
  const setPlaying = useCallback(value => {
    scheduler.cancel();
    setRequested(value);
  }, [scheduler]);
  useEffect(() => {
    scheduler.commit({ enabled: playing, speed, revision: replay.transition.revision, step: replay.step });
    return () => scheduler.cancel();
  }, [scheduler, playing, speed, replay.transition.revision, replay.step]);
  useEffect(() => {
    if (!replay.active || replay.atEnd || replay.loading) {
      // External session/end acknowledgement clears the playback request.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setRequested(false);
    }
  }, [replay.active, replay.atEnd, replay.loading]);
  useEffect(() => () => scheduler.dispose(), [scheduler]);
  return { playing, setPlaying };
}
