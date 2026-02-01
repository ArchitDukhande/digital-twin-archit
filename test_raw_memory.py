from layers.raw_memory import RawMemory

rm = RawMemory()
print(f"\nTotal chunks: {len(rm.raw_chunks)}")
print("\nChunks breakdown:")
for chunk in rm.raw_chunks:
    print(f"  {chunk['id']} - {chunk['type']} - {len(chunk['text'])} chars")
    if chunk['type'] == 'slack_message':
        print(f"    Timestamp: {chunk.get('timestamp')}")
        print(f"    Preview: {chunk['text'][:80]}...")
