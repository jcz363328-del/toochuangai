import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

if __name__ == '__main__':
    patterns = sys.argv[1:] or [
        'test_xiaoha*.py', 'test_task_runtime_concurrency.py', 'test_qa_chat*.py',
        'test_background_task_progress.py', 'test_manual_element_queue.py', 'test_canvas_api_proxy.py',
        'test_infinite_canvas_image_features.py', 'test_omnia*.py',
        'test_hd_batch_retry.py', 'test_portrait_hd_skin_lock.py',
        'test_outpaint_natural_blend.py', 'test_openrouter_input_size_limit.py',
    ]
    suite = unittest.TestSuite(unittest.defaultTestLoader.discover('tests', pattern=p) for p in patterns)
    with (Path(__file__).parent / 'regression.log').open('w', encoding='utf-8') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    print('tests:', result.testsRun, 'failures:', len(result.failures), 'errors:', len(result.errors))
    for test, details in result.failures + result.errors:
        print(test.id(), details.splitlines()[-1][:400])
    sys.exit(not result.wasSuccessful())
