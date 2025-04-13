from your_module import CommandProcessor

def test_command_parsing():
    processor = CommandProcessor()
    
    # Test translation command
    cmd = processor.process_command("Harmon translate this to French")
    assert cmd['command_type'] == 'translate'
    assert cmd['parameters']['target_language'] == 'french'
    
    # Test wake word without command
    cmd = processor.process_command("Harmon what do you think?")
    assert cmd['command_type'] == 'general_question'