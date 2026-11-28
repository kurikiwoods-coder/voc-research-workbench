"""M09-B runtime acceptance and quality gates with the approved local model."""

from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass
import math
import os
import unittest
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from src.discovery.embedding_inputs import FixtureRecord, MentionEvidence, OfflineEvidence
from src.discovery.topic_runs import TopicRuns
from src.discovery.topics import TopicConfig, cluster_offline
from src.raw_store.registry_versions import RegistryVersions
from src.raw_store.relations import RelationStore
from test_m09_actual_model import approved_backend
import test_m06_mentions as mentions


@dataclass(frozen=True)
class Example:
    theme: str | None
    product: str
    language: str
    text: str


SCALE, FRYER = mentions.PRODUCT_A, mentions.PRODUCT_B
EN, ZH = "en-US", "zh-CN"
EXAMPLES = (
    Example("offline", SCALE, EN, "The scale should keep working offline without internet access."),
    Example("offline", FRYER, EN, "The air fryer should still work offline when the internet goes down."),
    Example("offline", SCALE, EN, "Let me use all the weighing controls offline without a Wi-Fi connection."),
    Example("offline", FRYER, EN, "I want cooking controls to remain available offline when Wi-Fi is down."),
    Example("offline", SCALE, ZH, "厨房秤在家里断网以后也应该能离线运行。"),
    Example("offline", FRYER, ZH, "家里断网时，空气炸锅也应该能正常离线工作。"),
    Example("offline", SCALE, ZH, "希望没有网络或者无线连接时，秤仍能离线操作。"),
    Example("offline", FRYER, ZH, "没有网络时还能离线操作空气炸锅的烹饪功能。"),
    Example("washing", SCALE, EN, "I want the scale tray to be removable and safe to clean in the dishwasher."),
    Example("washing", FRYER, EN, "Make the air fryer basket removable so I can clean it in the dishwasher."),
    Example("washing", SCALE, EN, "The weighing tray should lift out easily for cleaning in the dishwasher."),
    Example("washing", FRYER, EN, "I need a detachable cooking basket that can be washed in the dishwasher."),
    Example("washing", SCALE, ZH, "希望厨房秤的称重盘可以拆下来，放进洗碗机清洗。"),
    Example("washing", FRYER, ZH, "空气炸锅的炸篮应该能拆卸，方便放进洗碗机清洗。"),
    Example("washing", SCALE, ZH, "秤盘能拿下来用洗碗机洗就好，手洗太费劲。"),
    Example("washing", FRYER, ZH, "可拆下的炸篮能直接用洗碗机清洁就好了。"),
    Example(None, SCALE, EN, "The display on the scale is too dim to read in the morning sun."),
    Example(None, FRYER, EN, "The completion alarm on the fryer is loud enough to wake a sleeping child."),
    Example(None, SCALE, ZH, "厨房秤的电池不到一小时就没有电了。"),
    Example(None, FRYER, ZH, "空气炸锅的退货箱里没有保修卡。"),
    Example(None, SCALE, EN, "I wish the scale came in a brighter shade of purple."),
    Example(None, FRYER, ZH, "空气炸锅升温慢，烤面包时外皮一直不脆。"),
)
TOPIC_CUES = {
    "offline": ("offline", "internet", "离线", "断网", "网络"),
    "washing": ("dishwasher", "洗碗机", "清洗", "拆卸"),
}
HOLDOUT = (
    Example("delay", SCALE, EN, "Let me set a delay timer so the scale starts automatically after ten minutes."),
    Example("delay", FRYER, EN, "I want to delay the cooking start and have the air fryer turn on automatically."),
    Example("delay", SCALE, EN, "The scale needs a delayed start timer that turns it on after a countdown."),
    Example("delay", FRYER, EN, "I want a delay timer to start cooking at a scheduled time."),
    Example("delay", SCALE, ZH, "希望厨房秤增加延迟启动定时器，倒计时结束后自动打开。"),
    Example("delay", FRYER, ZH, "希望空气炸锅可以预约，定时器结束后延迟启动。"),
    Example("delay", SCALE, ZH, "我想设定定时器，让厨房秤延迟启动并自动开机。"),
    Example("delay", FRYER, ZH, "我想用定时器延迟启动空气炸锅，让它在预约时间自动开始。"),
    Example("sound", SCALE, EN, "The scale button beep is too loud and I want to lower its volume."),
    Example("sound", FRYER, EN, "Please add a volume setting to mute the loud cooking completion beep."),
    Example("sound", SCALE, EN, "I need to mute the scale beeps or set the alert volume lower at night."),
    Example("sound", FRYER, EN, "Air fryer alerts need an adjustable volume and a quiet mute mode."),
    Example("sound", SCALE, ZH, "称重时秤的提示音太响了，我想调低音量或者静音。"),
    Example("sound", FRYER, ZH, "空气炸锅完成提示音太大，希望可以调节音量和静音。"),
    Example("sound", SCALE, ZH, "厨房秤的按键提示音有点吵，想要音量调节和静音功能。"),
    Example("sound", FRYER, ZH, "建议增加提示音的音量设置，晚上能把空气炸锅静音。"),
    Example(None, SCALE, EN, "The scale should come with a wooden carrying case to protect it in a suitcase."),
    Example(None, FRYER, EN, "It would be nicer if the fryer came in a dark green color."),
    Example(None, SCALE, ZH, "厨房秤的数字在阳光下看不清楚。"),
    Example(None, FRYER, ZH, "希望空气炸锅的包装用可回收纸板，减少泡沫塑料。"),
    Example(None, SCALE, EN, "I want the scale to show the result in ounces as a fraction."),
    Example(None, FRYER, ZH, "空气炸锅的炸篮放进洗碗机以后生锈了。"),
)
HOLDOUT_CUES = {
    "delay": ("delay", "timer", "定时器", "延迟", "预约"),
    "sound": ("volume", "beep", "mute", "音量", "静音", "提示音"),
}
PINNED_CONFIG = TopicConfig(
    random_seed=19, n_neighbors=6, n_components=2, min_dist=0.1,
    min_cluster_size=5, min_samples=5, top_n_words=10,
)
quality_gate = unittest.skipUnless(
    os.environ.get("VOC_RUN_M09_TOPIC_QUALITY_GATE") == "1",
    "set VOC_RUN_M09_TOPIC_QUALITY_GATE=1 to run the clustering quality gates",
)


@unittest.skipUnless(
    os.environ.get("VOC_M09_MODEL_DIR") and os.environ.get("VOC_M09_MODEL_MANIFEST"),
    "requires the separately provisioned local model and BERTopic runtime",
)
class ApprovedTopicTest(unittest.TestCase):
    fixture_examples = None

    def setUp(self):
        self.case = mentions.MentionTests()
        self.addCleanup(self.case.doCleanups)
        self.backend = approved_backend()
        self.addCleanup(self.backend.close)

        # Pin generated lineage IDs because M09-A sorts on their digests before fitting.
        fixture_ids = iter(uuid5(NAMESPACE_URL, f"voc-m09-b-fixture/{index}") for index in range(1_000))
        with ExitStack() as stack:
            for module in ("studies", "imports", "mentions"):
                stack.enter_context(patch(f"src.raw_store.{module}.uuid4", side_effect=fixture_ids))
            self.case.setUp()
            examples = EXAMPLES if self.fixture_examples is None else self.fixture_examples
            self.refs, self.examples_by_id, self.evidence = self.build_fixture(examples)

    def build_fixture(self, fixture_examples):
        self.case.bind_products((SCALE, FRYER))
        examples = {}
        drafts = []
        proposals = []
        for index, example in enumerate(fixture_examples):
            key = f"topic-{index}"
            _, interval = self.case.add_quote(key, example.text)
            examples[key] = (example, interval)
            drafts.append(self.case.member(key, interval))
            proposals.append(self.case.proposal(key, interval, example.product))
        published = self.case.publish(drafts, proposals=tuple(proposals))
        refs = []
        reviews = []
        for member in published["members"]:
            example, interval = examples[member["ref"]]
            record = FixtureRecord(self.case.study, self.case.scope, "v1", interval.record_id, interval.raw_sha256)
            refs.append(MentionEvidence(
                record, published["revision"], member["mention_id"], member["evidence_ids"][0], example.language,
            ))
            reviews.append(self.case.decision(member, example.product))
        self.case.review(*reviews)

        evidence = OfflineEvidence(
            study_id=self.case.study, scope_id=self.case.scope, scope_version="v1", mentions=self.case.store,
            registry=RegistryVersions(RelationStore(self.case.db)),
            fixture_records=tuple(ref.record for ref in refs),
        )
        by_id = {
            evidence.read(ref).lineage.document_id: examples[member["ref"]][0]
            for ref, member in zip(refs, published["members"], strict=True)
        }
        return tuple(refs), by_id, evidence

    def check_topics(self, scenario, cues, **config_options):
        options = dict(
            registry_version=mentions.CATALOG, analysis_language="zh-CN", output_language="en-US",
            cache_dir=self.case.db.path.parent / "topic-acceptance-embeddings", **config_options,
        )
        result = cluster_offline(self.evidence, self.backend, self.refs, **options)
        replay = cluster_offline(self.evidence, self.backend, self.refs[::-1], **options)
        assignments = {row.document_id: row.topic_id for row in result.assignments}
        topics = {row.topic_id: row for row in result.topics}
        counts = Counter(assignments.values())
        expected = self.examples_by_id
        noise_count = sum(assignments.get(key) == -1 for key, example in expected.items() if example.theme is None)
        replay_equal = result == replay
        print(
            f"M09-B scenario={scenario} groups={len(cues)} documents={len(expected)} topics={len(topics)} "
            f"outliers={counts[-1]} expected_noise_outliers={noise_count} replay_equal={replay_equal}",
            flush=True,
        )
        self.assertEqual(len(result.assignments), len(expected))
        self.assertEqual(tuple(assignments), tuple(sorted(expected)))
        self.assertEqual(len(result.topics), len(topics))
        self.assertEqual(set(topics), set(counts) - {-1})
        self.assertEqual(result.status, "clustered")
        for topic_id, topic in topics.items():
            self.assertEqual(topic.member_count, counts[topic_id])
            self.assertTrue(topic.keywords)
            for keyword in topic.keywords:
                self.assertTrue(keyword.term.strip())
                self.assertTrue(math.isfinite(keyword.weight) and keyword.weight > 0)
        self.assertEqual(result, replay)

        matched_topics = set()
        for theme, theme_cues in cues.items():
            expected_ids = {key for key, example in expected.items() if example.theme == theme}
            overlaps = Counter(assignments[key] for key in expected_ids if assignments[key] != -1)
            best_id = min(overlaps, key=lambda topic_id: (-overlaps[topic_id], topic_id)) if overlaps else None
            hits = overlaps[best_id]
            size = counts[best_id]
            print(
                f"M09-B scenario={scenario} theme={theme} covered={hits}/{len(expected_ids)} purity={hits}/{size}",
                flush=True,
            )
            with self.subTest(theme=theme):
                self.assertIsNotNone(best_id)
                self.assertNotIn(best_id, matched_topics)
                matched_topics.add(best_id)
                matched = [expected[key] for key in expected_ids if assignments[key] == best_id]
                self.assertEqual({example.language for example in matched}, {EN, ZH})
                self.assertEqual({example.product for example in matched}, {SCALE, FRYER})
                terms = [keyword.term.casefold() for keyword in topics[best_id].keywords]
                for ascii_cue, language in ((True, EN), (False, ZH)):
                    self.assertTrue(
                        any(cue in term for cue in theme_cues if cue.isascii() == ascii_cue for term in terms),
                        f"{theme} has no {language} keyword cue in {terms}",
                    )
                self.assertGreaterEqual(4 * hits, 3 * len(expected_ids), "require at least 75% theme recall")
                self.assertGreaterEqual(4 * hits, 3 * size, "require at least 75% topic precision")
        self.assertGreaterEqual(noise_count, 1)

    def test_production_defaults_bilingual_topics_noise_and_replay(self):
        self.check_topics("frozen-defaults", TOPIC_CUES)

    @quality_gate
    def test_bilingual_topics_noise_and_replay(self):
        self.check_topics("frozen-pinned", TOPIC_CUES, config=PINNED_CONFIG)


@unittest.skipUnless(
    os.environ.get("VOC_M09_MODEL_DIR") and os.environ.get("VOC_M09_MODEL_MANIFEST"),
    "requires the separately provisioned local model and BERTopic runtime",
)
class HoldoutTopicQualityTest(ApprovedTopicTest):
    fixture_examples = HOLDOUT

    @quality_gate
    def test_production_defaults_bilingual_topics_noise_and_replay(self):
        self.check_topics("holdout-defaults", HOLDOUT_CUES)

    @quality_gate
    def test_bilingual_topics_noise_and_replay(self):
        self.check_topics("holdout-pinned", HOLDOUT_CUES, config=PINNED_CONFIG)


@unittest.skipUnless(
    os.environ.get("VOC_M09_MODEL_DIR") and os.environ.get("VOC_M09_MODEL_MANIFEST"),
    "requires the separately provisioned local model and BERTopic runtime",
)
class ApprovedTopicPersistenceTest(unittest.TestCase):
    def test_native_model_cold_replay_and_exact_evidence(self):
        fixture = ApprovedTopicTest()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()

        def authorize(study_id):
            return study_id == fixture.case.study

        producer = TopicRuns(fixture.case.db, fixture.evidence, authorize_project=authorize)
        first = producer.create(
            fixture.backend, fixture.refs, request_id="m09-native-first",
            registry_version=mentions.CATALOG, analysis_language=ZH, output_language=EN,
        )
        self.assertEqual(first["status"], "clustered")
        self.assertEqual(len(first["members"]), len(EXAMPLES))
        self.assertTrue(any(topic["topic_id"] == -1 for topic in first["topics"]))
        for member in first["members"]:
            doc_id = member["document_id"]
            self.assertEqual(member["raw_topic_id"], member["topic_id"])
            self.assertIsNotNone(member["hdbscan_cluster_id"])
            self.assertIsNotNone(member["membership_probability"])
            self.assertEqual(
                producer.evidence_for(first["run_id"], doc_id).original_text,
                fixture.examples_by_id[doc_id].text,
            )
        self.assertEqual(first["quality"]["m09_b_synthetic_purity"], [[8, 11], [8, 12], [8, 13]])

        backend = approved_backend()
        self.addCleanup(backend.close)
        consumer = TopicRuns(fixture.case.db, fixture.evidence, authorize_project=authorize)
        replay = consumer.replay(first["run_id"], backend, request_id="m09-native-replay")
        self.assertNotEqual(replay["run_id"], first["run_id"])
        self.assertEqual(replay["replay_of"], first["run_id"])
        self.assertTrue(consumer.compare(first["run_id"], replay["run_id"])["same_result"])
