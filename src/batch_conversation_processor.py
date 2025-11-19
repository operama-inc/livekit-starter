#!/usr/bin/env python3
"""
Batch Conversation Processor - Runs multiple LiveKit conversations in parallel
"""
import asyncio
import logging
import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import sys
import random

sys.path.insert(0, str(Path(__file__).parent.parent))

from livekit_conversation_runner import LiveKitConversationRunner
from voice_conversation_generator.services import PersonaService
from voice_conversation_generator.models import ConversationMetrics

from dotenv import load_dotenv

load_dotenv(".env.local")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BatchConversationProcessor:
    """Processes multiple LiveKit conversations in parallel"""

    def __init__(
        self,
        max_parallel: int = 5,
        output_dir: str = "data/livekit_conversations"
    ):
        """Initialize batch processor

        Args:
            max_parallel: Maximum concurrent conversations
            output_dir: Directory for output files
        """
        self.max_parallel = max_parallel
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Create runner instance
        self.runner = LiveKitConversationRunner(output_dir=output_dir)

        # Load personas
        self.persona_service = PersonaService()
        self.persona_service.load_default_personas()

        # Track progress
        self.completed = 0
        self.failed = 0
        self.total = 0

    async def run_batch(
        self,
        count: int,
        customer_personas: Optional[List[str]] = None,
        support_personas: Optional[List[str]] = None,
        max_turns_range: tuple = (3, 8),
        record_audio: bool = True,
        record_per_track: bool = True
    ) -> Dict[str, Any]:
        """Run a batch of conversations

        Args:
            count: Number of conversations to generate
            customer_personas: List of customer persona IDs (random if None)
            support_personas: List of support persona IDs (random if None)
            max_turns_range: Min and max turns for conversations
            record_audio: Whether to record composite audio
            record_per_track: Whether to record per-track audio

        Returns:
            Summary of batch results
        """
        self.total = count
        self.completed = 0
        self.failed = 0

        # Get available personas
        if not customer_personas:
            customer_personas = list(self.persona_service.customer_personas.keys())
        if not support_personas:
            support_personas = list(self.persona_service.support_personas.keys())

        # Generate conversation configurations
        conversations = []
        for i in range(count):
            customer_id = random.choice(customer_personas)
            support_id = random.choice(support_personas)
            max_turns = random.randint(*max_turns_range)

            conversations.append({
                'index': i,
                'customer_persona_id': customer_id,
                'support_persona_id': support_id,
                'max_turns': max_turns,
                'record_audio': record_audio,
                'record_per_track': record_per_track
            })

        logger.info(f"Starting batch of {count} conversations")
        logger.info(f"Max parallel: {self.max_parallel}")
        logger.info(f"Customer personas: {customer_personas}")
        logger.info(f"Support personas: {support_personas}")

        # Run conversations with concurrency control
        semaphore = asyncio.Semaphore(self.max_parallel)
        tasks = [
            self._run_with_semaphore(semaphore, conv)
            for conv in conversations
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        successful_conversations = []
        failed_conversations = []

        for conv, result in zip(conversations, results):
            if isinstance(result, Exception):
                failed_conversations.append({
                    'conversation': conv,
                    'error': str(result)
                })
                self.failed += 1
                logger.error(f"Conversation {conv['index']} failed: {result}")
            else:
                successful_conversations.append(result)
                self.completed += 1

        # Generate summary report
        summary = self._generate_summary(
            successful_conversations,
            failed_conversations
        )

        # Save summary to file
        summary_file = self.output_dir / f"batch_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)

        logger.info(f"Batch completed: {self.completed}/{self.total} successful")
        logger.info(f"Summary saved to: {summary_file}")

        return summary

    async def _run_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        conversation_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run a single conversation with semaphore control"""
        async with semaphore:
            index = conversation_config['index']
            logger.info(f"Starting conversation {index + 1}/{self.total}")

            try:
                # Add delay between conversation starts to avoid overwhelming the system
                if index > 0:
                    await asyncio.sleep(2)

                result = await self.runner.run_conversation(
                    customer_persona_id=conversation_config['customer_persona_id'],
                    support_persona_id=conversation_config['support_persona_id'],
                    max_turns=conversation_config['max_turns'],
                    record_audio=conversation_config['record_audio'],
                    record_per_track=conversation_config['record_per_track']
                )

                logger.info(f"Completed conversation {index + 1}/{self.total}")
                self._print_progress()

                return result

            except Exception as e:
                logger.error(f"Failed conversation {index + 1}/{self.total}: {e}")
                self._print_progress()
                raise

    def _print_progress(self):
        """Print current progress"""
        completed = self.completed + self.failed
        percentage = (completed / self.total) * 100 if self.total > 0 else 0
        logger.info(f"Progress: {completed}/{self.total} ({percentage:.1f}%) - "
                    f"Success: {self.completed}, Failed: {self.failed}")

    def _generate_summary(
        self,
        successful_conversations: List[Dict],
        failed_conversations: List[Dict]
    ) -> Dict[str, Any]:
        """Generate summary report of batch results"""
        summary = {
            'timestamp': datetime.now().isoformat(),
            'total_conversations': self.total,
            'successful': self.completed,
            'failed': self.failed,
            'success_rate': (self.completed / self.total * 100) if self.total > 0 else 0,

            'persona_distribution': {
                'customer': {},
                'support': {}
            },

            'turn_distribution': {},

            'successful_conversations': successful_conversations,
            'failed_conversations': failed_conversations,

            'recordings': {
                'composite_count': 0,
                'per_track_count': 0,
                'total_files': 0
            }
        }

        # Analyze persona distribution
        for conv in successful_conversations:
            customer = conv.get('customer_persona', 'unknown')
            support = conv.get('support_persona', 'unknown')
            turns = conv.get('max_turns', 0)

            summary['persona_distribution']['customer'][customer] = \
                summary['persona_distribution']['customer'].get(customer, 0) + 1
            summary['persona_distribution']['support'][support] = \
                summary['persona_distribution']['support'].get(support, 0) + 1

            turn_key = str(turns)
            summary['turn_distribution'][turn_key] = \
                summary['turn_distribution'].get(turn_key, 0) + 1

            # Count recordings
            recordings = conv.get('recordings', {})
            if 'composite' in recordings:
                summary['recordings']['composite_count'] += 1
            summary['recordings']['per_track_count'] += len([
                r for r in recordings if r.startswith('track_')
            ])
            summary['recordings']['total_files'] += len(recordings)

        return summary

    async def run_diverse_batch(
        self,
        count: int
    ) -> Dict[str, Any]:
        """Run a batch with diverse persona combinations

        This ensures good coverage of different customer types and scenarios
        """
        # Define persona combinations for diversity
        persona_combinations = [
            # Angry customers
            ('angry_insufficient_funds', 'default'),
            ('angry_billing', 'default'),

            # Confused customers
            ('confused_elderly', 'default'),
            ('confused_technical', 'default'),

            # Cooperative customers
            ('cooperative_parent', 'default'),
            ('friendly_billing', 'default'),

            # Edge cases
            ('edge_case_nightmare', 'default'),
        ]

        # Create conversation configs cycling through combinations
        conversations = []
        for i in range(count):
            customer_id, support_id = persona_combinations[i % len(persona_combinations)]
            max_turns = 3 + (i % 5)  # Vary from 3 to 7 turns

            conversations.append({
                'index': i,
                'customer_persona_id': customer_id,
                'support_persona_id': support_id,
                'max_turns': max_turns,
                'record_audio': True,
                'record_per_track': True
            })

        logger.info(f"Running diverse batch of {count} conversations")

        # Run with controlled concurrency
        semaphore = asyncio.Semaphore(self.max_parallel)
        tasks = [
            self._run_with_semaphore(semaphore, conv)
            for conv in conversations
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results (same as run_batch)
        successful_conversations = []
        failed_conversations = []

        for conv, result in zip(conversations, results):
            if isinstance(result, Exception):
                failed_conversations.append({
                    'conversation': conv,
                    'error': str(result)
                })
                self.failed += 1
            else:
                successful_conversations.append(result)
                self.completed += 1

        summary = self._generate_summary(
            successful_conversations,
            failed_conversations
        )

        # Save summary
        summary_file = self.output_dir / f"diverse_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)

        return summary


async def main():
    """Run batch conversations with different configurations"""
    import argparse

    parser = argparse.ArgumentParser(description='Batch LiveKit Conversation Processor')
    parser.add_argument('--count', type=int, default=10,
                        help='Number of conversations to generate')
    parser.add_argument('--parallel', type=int, default=5,
                        help='Maximum parallel conversations')
    parser.add_argument('--diverse', action='store_true',
                        help='Use diverse persona combinations')
    parser.add_argument('--customer', type=str, nargs='+',
                        help='Specific customer personas to use')
    parser.add_argument('--support', type=str, nargs='+',
                        help='Specific support personas to use')
    parser.add_argument('--min-turns', type=int, default=3,
                        help='Minimum conversation turns')
    parser.add_argument('--max-turns', type=int, default=8,
                        help='Maximum conversation turns')

    args = parser.parse_args()

    # Create processor
    processor = BatchConversationProcessor(
        max_parallel=args.parallel
    )

    # Run batch
    if args.diverse:
        summary = await processor.run_diverse_batch(args.count)
    else:
        summary = await processor.run_batch(
            count=args.count,
            customer_personas=args.customer,
            support_personas=args.support,
            max_turns_range=(args.min_turns, args.max_turns)
        )

    # Print summary
    print("\n" + "=" * 60)
    print("BATCH PROCESSING COMPLETED")
    print("=" * 60)
    print(f"Total conversations: {summary['total_conversations']}")
    print(f"Successful: {summary['successful']}")
    print(f"Failed: {summary['failed']}")
    print(f"Success rate: {summary['success_rate']:.1f}%")
    print("\nPersona Distribution:")
    print(f"  Customer: {summary['persona_distribution']['customer']}")
    print(f"  Support: {summary['persona_distribution']['support']}")
    print("\nTurn Distribution:")
    print(f"  {summary['turn_distribution']}")
    print("\nRecordings:")
    print(f"  Composite: {summary['recordings']['composite_count']}")
    print(f"  Per-track: {summary['recordings']['per_track_count']}")
    print(f"  Total files: {summary['recordings']['total_files']}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())