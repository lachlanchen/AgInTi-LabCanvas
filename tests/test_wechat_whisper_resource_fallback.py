import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agentic_tools/wechat_gui_agent/scripts"))
import wechat_voice_transcribe as voice


class WhisperResourceFallbackTests(unittest.TestCase):
    def test_cuda_oom_retries_same_model_on_cpu_once(self):
        failed = mock.Mock()
        failed.transcribe.side_effect = RuntimeError('CUDA out of memory')
        cpu = mock.Mock()
        cpu.transcribe.return_value = {'language': 'zh', 'segments': [
            {'start': 0, 'end': 2, 'text': 'Verified speech'}]}
        load = mock.Mock(side_effect=[failed, cpu])
        empty_cache = mock.Mock()
        with mock.patch.dict(sys.modules, {
            'whisper': SimpleNamespace(load_model=load),
            'torch': SimpleNamespace(cuda=SimpleNamespace(empty_cache=empty_cache)),
        }):
            result = voice.transcribe_wav_openai_whisper(Path('source.wav'), model='turbo', device='cuda', language='zh')
        self.assertEqual(load.call_args_list, [mock.call('turbo', device='cuda'), mock.call('turbo', device='cpu')])
        cpu.transcribe.assert_called_once_with('source.wav', fp16=False, language='zh')
        empty_cache.assert_called_once()
        self.assertEqual(result['text'], 'Verified speech')
        self.assertEqual(result['device'], 'cpu')

    def test_non_resource_error_does_not_retry(self):
        load = mock.Mock(side_effect=RuntimeError('Invalid audio'))
        with mock.patch.dict(sys.modules, {'whisper': SimpleNamespace(load_model=load)}):
            with self.assertRaisesRegex(RuntimeError, 'Invalid audio'):
                voice.transcribe_wav_openai_whisper(Path('source.wav'), model='turbo', device='cuda')
        self.assertEqual(load.call_count, 1)

    def test_cpu_failure_does_not_loop(self):
        load = mock.Mock(side_effect=RuntimeError('out of memory'))
        with mock.patch.dict(sys.modules, {'whisper': SimpleNamespace(load_model=load)}):
            with self.assertRaises(RuntimeError):
                voice.transcribe_wav_openai_whisper(Path('source.wav'), model='turbo', device='cpu')
        self.assertEqual(load.call_count, 1)
