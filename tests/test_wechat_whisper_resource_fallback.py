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
        set_threads = mock.Mock()
        with mock.patch.dict(voice.os.environ, {'WECHAT_WHISPER_CPU_THREADS': '4'}), mock.patch.dict(sys.modules, {
            'whisper': SimpleNamespace(load_model=load),
            'torch': SimpleNamespace(cuda=SimpleNamespace(empty_cache=empty_cache),
                                     get_num_threads=lambda: 14, set_num_threads=set_threads),
        }):
            result = voice.transcribe_wav_openai_whisper(Path('source.wav'), model='turbo', device='cuda', language='zh')
        self.assertEqual(load.call_args_list, [mock.call('turbo', device='cuda'), mock.call('turbo', device='cpu')])
        cpu.transcribe.assert_called_once_with('source.wav', fp16=False, language='zh')
        empty_cache.assert_called_once()
        self.assertEqual(result['text'], 'Verified speech')
        self.assertEqual(result['device'], 'cpu')
        self.assertEqual(set_threads.call_args_list, [mock.call(4), mock.call(14)])

    def test_non_resource_error_does_not_retry(self):
        load = mock.Mock(side_effect=RuntimeError('Invalid audio'))
        with mock.patch.dict(sys.modules, {'whisper': SimpleNamespace(load_model=load)}):
            with self.assertRaisesRegex(RuntimeError, 'Invalid audio'):
                voice.transcribe_wav_openai_whisper(Path('source.wav'), model='turbo', device='cuda')
        self.assertEqual(load.call_count, 1)

    def test_driver_mismatch_falls_back_without_calling_broken_cuda_cleanup(self):
        for error in ('NVML_SUCCESS == nvmlInit_v2 INTERNAL ASSERT FAILED',
                      'Failed to initialize NVML: Driver/library version mismatch'):
            with self.subTest(error=error):
                cpu = mock.Mock()
                cpu.transcribe.return_value = {'language': 'en', 'segments': [{'start': 0, 'end': 2, 'text': 'Speech'}]}
                load = mock.Mock(side_effect=[RuntimeError(error), cpu])
                empty_cache = mock.Mock(side_effect=RuntimeError('driver still broken'))
                with mock.patch.dict(sys.modules, {
                    'whisper': SimpleNamespace(load_model=load),
                    'torch': SimpleNamespace(cuda=SimpleNamespace(empty_cache=empty_cache),
                                             get_num_threads=lambda: 8, set_num_threads=mock.Mock()),
                }):
                    result = voice.transcribe_wav_openai_whisper(Path('source.wav'), model='turbo', device='cuda')
                self.assertEqual(result['device'], 'cpu')
                self.assertEqual(result['device_fallback_reason'], 'cuda_driver_unavailable')
                self.assertEqual(load.call_args_list, [mock.call('turbo', device='cuda'), mock.call('turbo', device='cpu')])
                empty_cache.assert_not_called()

    def test_cpu_failure_does_not_loop(self):
        load = mock.Mock(side_effect=RuntimeError('out of memory'))
        set_threads = mock.Mock()
        with mock.patch.dict(voice.os.environ, {'WECHAT_WHISPER_CPU_THREADS': '4'}), mock.patch.dict(sys.modules, {'whisper': SimpleNamespace(load_model=load),
                'torch': SimpleNamespace(get_num_threads=lambda: 2, set_num_threads=set_threads)}):
            with self.assertRaises(RuntimeError):
                voice.transcribe_wav_openai_whisper(Path('source.wav'), model='turbo', device='cpu')
        self.assertEqual(load.call_count, 1)
        self.assertEqual(set_threads.call_args_list, [mock.call(2), mock.call(2)])
