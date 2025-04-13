import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Cerebras API details
CEREBRAS_API_KEY = os.getenv('CEREBRAS_API_KEY')
CEREBRAS_API_ENDPOINT = os.getenv('CEREBRAS_API_ENDPOINT')

def generate_summary(transcript_segments, max_length=2):
    """
    Generate a summary of the transcript segments using Cerebras LLM
    
    Args:
        transcript_segments: List of transcript segments with speaker and text
        max_length: Maximum number of sentences in the summary
        
    Returns:
        A string containing the summary
    """
    if not CEREBRAS_API_KEY:
        return "API key not configured. Please set the CEREBRAS_API_KEY environment variable."
    
    # Format the transcript for the prompt
    formatted_transcript = ""
    for segment in transcript_segments:
        formatted_transcript += f"Speaker {segment['speaker']}: {segment['text']}\n"
    
    # Create the prompt for summarization
    prompt = f"""
    I need a concise summary of the following conversation transcript. 
    Keep it to {max_length} sentences and focus on the key points.
    
    Transcript:
    {formatted_transcript}
    
    Summary:
    """
    
    try:
        # Make request to Cerebras API
        response = requests.post(
            CEREBRAS_API_ENDPOINT,
            headers={
                "Authorization": f"Bearer {CEREBRAS_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3-1-70b-instruct",  # Use the appropriate model name
                "prompt": prompt,
                "max_tokens": 150,
                "temperature": 0.7
            }
        )
        
        response_data = response.json()
        summary = response_data.get('completion', 'Failed to generate summary.')
        
        return summary.strip()
    
    except Exception as e:
        print(f"Error generating summary: {str(e)}")
        return f"Error generating summary: {str(e)}"

def generate_solutions(last_point, num_solutions=3):
    """
    Generate solutions for a given discussion point using Cerebras LLM
    
    Args:
        last_point: The last discussion point to generate solutions for
        num_solutions: Number of solutions to generate
        
    Returns:
        A list of solution strings
    """
    if not CEREBRAS_API_KEY:
        return ["API key not configured. Please set the CEREBRAS_API_KEY environment variable."]
    
    # Create the prompt for solution generation
    prompt = f"""
    Given this discussion point: "{last_point}"
    
    Generate {num_solutions} practical and specific solutions or ideas. 
    Be concise but specific for each solution.
    Format your response as a numbered list.
    """
    
    try:
        # Make request to Cerebras API
        response = requests.post(
            CEREBRAS_API_ENDPOINT,
            headers={
                "Authorization": f"Bearer {CEREBRAS_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3-1-70b-instruct",  # Use the appropriate model name
                "prompt": prompt,
                "max_tokens": 200,
                "temperature": 0.7
            }
        )
        
        response_data = response.json()
        solutions_text = response_data.get('completion', '')
        
        # Parse the solutions from the response
        solutions = []
        lines = solutions_text.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith('-')):
                # Remove the number/bullet and any following punctuation
                solution = line.split('.', 1)[-1].strip() if '.' in line else line
                solution = solution.split(')', 1)[-1].strip() if ')' in solution else solution
                solution = solution.lstrip('- ').strip()
                if solution:
                    solutions.append(solution)
        
        # Ensure we have the requested number of solutions
        while len(solutions) < num_solutions:
            solutions.append(f"Solution {len(solutions)+1}")
        
        return solutions[:num_solutions]
    
    except Exception as e:
        print(f"Error generating solutions: {str(e)}")
        return [f"Error generating solutions: {str(e)}"]

def extract_last_point(recent_transcript_segments):
    """
    Extract the last meaningful point from recent transcript segments
    
    Args:
        recent_transcript_segments: List of recent transcript segments
        
    Returns:
        A string containing the extracted last point
    """
    if not recent_transcript_segments:
        return "No recent transcript available."
    
    # Get the most recent segment
    last_segment = sorted(recent_transcript_segments, key=lambda x: x.get('timestamp', 0), reverse=True)[0]
    last_point = last_segment.get('text', 'No text available')
    
    return last_point
