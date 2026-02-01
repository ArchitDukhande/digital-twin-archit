December 4, 2025

Archit  9:58 AM  
Hi! Thanks for adding me. I’ve joined AWS and Slack. Excited to get started.

CTO  10:02 AM  
Welcome, Archit.

Archit  10:10 AM  
I’m getting familiar with how the model works and the overall setup.  
To understand the model behavior better, the next step would be to run some tests. Before I do that, is there a preferred way the team currently tests the endpoint or any specific audio samples you want me to use?

CTO  10:12 AM  
On the product side, we directly call the SageMaker endpoint. If you want to test locally, you basically start the server using the code and then call into the endpoint.

Archit  10:46 AM  
Okay, I’ll run a few small tests on the SageMaker endpoint to understand the model behavior. I’ll use short audio clips and keep the load minimal.

CTO  10:46 AM  
Sounds good.  
It’s probably better if we schedule some time with Ex-Intern since most of the code is written by him.

Archit  10:48 AM  
Sounds good. I’d appreciate a session with Ex-Intern so I can get acquainted with the codebase and understand the design better. Just let me know a time that works.


December 7, 2025

CTO  7:05 PM 
So As per yesterday's discussion, you main goal is cost optimization and refactoring of the ML Infrastructure.

Archit  7:03 PM  
We were planning to schedule a shutdown today.  
11pm to 7am ET?

CTO  7:05 PM  
Yes.  
How are you planning to do it?

Archit  7:14 PM  
I only have a theoretical understanding of doing it using EventBridge cron schedules and Lambda.  
I was in the library, I’ll go home and work on the scripts while having dinner.

CTO  7:15 PM  
No, let’s not use EventBridge. That adds a lot of complexity.  
SageMaker has its own cron-based scheduled scaling. That should work.

Archit  7:16 PM  
Okay, I’ll check the documentation.


December 8, 2025

Archit  10:32 AM  
I went through the scheduled scaling docs. There are two ways to do this, either via CLI or directly through the console. Console looks simpler.

CTO  10:35 AM  
Yes, console is fine.

Archit  10:44 AM  
Before I apply anything on the prod endpoint, I just want to double check with you. I haven’t done scheduled scaling on SageMaker before and don’t want to cause any disruption.

CTO  10:54 AM  
Let me do it then.


December 10, 2025

Archit  8:58 AM  
Quick check: the scale-down is currently set to midnight PT, not 11pm ET. Just wanted to make sure that’s intentional.

CTO  9:03 AM  
This is what we want. We need to consider west coast users too.

Archit  9:08 AM  
Got it. One thing I noticed is that it didn’t fully scale down last night. It might be because the min/max was set to 0–1 instead of 0–0.

CTO  9:09 AM  
I suspect this might not work cleanly for SageMaker. If needed, we’ll explore alternatives.


December 12, 2025

Archit  12:17 PM  
I was reading more about this and wanted to confirm something. From the docs, it looks like scale-to-zero works properly only when using inference components. Our current setup looks like a classic real-time endpoint without inference components.

CTO  12:13 PM  
Oh, that’s a good point. I need to check that.

CTO  12:15 PM  
When the endpoint is at 0, the first inference requests can error until an instance finishes provisioning. This is expected.  
So we only scale to 0 during night time. If someone starts to use it, we can spin it up even at night. Only loses a few minutes.

Archit  12:23 PM  
That makes sense. I was thinking we could create a separate endpoint with inference components, set up scaling policies and CloudWatch alarms, and test scale-to-zero and wake-up behavior before replacing the current endpoint.

CTO  12:23 PM  
That should be safe enough. We can test on a new endpoint for sure.  
Do you want to play around with it?

Archit  12:25 PM  
Yeah, I’d like to try it. I’ll make sure I don’t touch the prod endpoint.


December 18, 2025

Archit  11:39 AM  
Major update: autoscaling works properly. I tested scale-to-zero and wake-up behavior using a polling script.  
From a fully cold state, it took about 6–9 minutes to get the first successful response. During that time, invoke requests failed with a no-capacity error, which seems expected while the inference component is starting.  
The desired copy count moved from 0 to 1 early, but the component stayed in an updating state for several minutes. Once the model returned a response, everything worked normally.

CTO  11:48 AM  
This is great. Roughly how long does it take to scale up?

Archit  11:49 AM  
About 6–9 minutes from a fully cold state to the first successful response.

CTO  11:51 AM  
Got it. This is expected behavior.  
Customer experience is important, so we should only scale to 0 during night time.


December 20, 2025

Archit  10:16 AM  
I tested scaling without invoking the endpoint. If I manually scale the inference component to 1, it takes about 3–4 minutes to get instances up.

CTO  10:17 AM  
Nice, so that’s an improvement over waiting for autoscaling to detect traffic.
But still, I had a word with SLPs and they said no waiting time. We will use this as a temporary fix, but we will need a permanent fix. It is saving 30% cost.

Archit  10:20 AM  
Yes, maybe kids have a less attention time, so I can try CPU or inferentia for cost control.

CTO  10:22 AM  
Yeah, try inferentia first then CPU


December 26, 2025

Archit  3:22 PM  
Hey, would it be okay if I create a separate test endpoint with inference components on inf1 (Inferentia)? I’m not fully sure the current model is Neuron compatible, and since Inferentia needs a different image and setup, I’d prefer keeping the current test endpoint intact.

Archit  3:28 PM  
Planning to try inf1.xlarge first. Cost is around $0.2 per hour.

CTO  10:09 AM  
Sure. Since the Docker image is provided by SageMaker, I’m fairly confident it’s available for Inferentia. But you can try.


December 29, 2025

Archit  10:57 AM  
Added a Neuron compilation POC script under a separate branch.  
I tried compiling on inf1 but hit a driver/device error, which looks like an AMI or kernel compatibility issue. I terminated that instance and am spinning up a new one with a compatible setup.

Archit  12:44 PM  
I’m basically stuck on the AMI issue. Latest AMIs don’t support inf1, and inf2 is expensive. Trying to use a plain AMI and manually install Neuron.


December 30, 2025

Archit  3:30 PM  
Neuron compilation is complete and the compiled model has been downloaded and verified.  
I’m packaging it into a tar file, uploading to S3, and then creating the inference component and endpoint.


January 2, 2026

Archit  2:26 PM  
Quick update: I switched resampling to torchaudio and removed librosa to avoid scipy dependencies. I added everything to requirements.txt, but the container is not auto-installing it, so torchaudio is missing at startup and the worker crashes on import.  
I also tried forced installs inside inference.py plus apt-get ffmpeg, but apt-get fails due to permission issues. It ends up in a crash loop.

Archit  2:27 PM  
I’m deleting the endpoint for now. It’s not the autoscaling one, so I can recreate it easily.

CTO  5:45 PM  
Let me check again.


January 18, 2026

Archit  2:39 PM  
If we ignore the first 3 warmup requests, the latency looks reasonable.

CTO  2:39 PM  
How does warm-up work?  
Is it just the first few requests being slow?  
What if you let the endpoint run for a few minutes and then invoke it?

Archit  2:42 PM  
Just letting the endpoint sit idle doesn’t warm it up by itself.  
I’ll keep it running for 5 minutes and test again to confirm.

CTO  2:45 PM  
FYI, I’m refactoring the original code now. Earlier I didn’t want to touch it since it worked, but if we’re changing decoding paths for Neuron, it’s impossible to do that cleanly without refactoring.

Archit  2:47 PM  
ffmpeg and WAV decoding was mainly for Neuron since librosa was failing there.

CTO  2:47 PM  
Yeah, on Neuron. It does seem more efficient.


January 19, 2026

Archit  4:33 PM  
Can I try CPU-only inference image on a compute-optimized instance?

CTO  4:34 PM  
Sure.

Archit  4:44 PM  
Can you increase the quota to 1 for that instance type?

CTO  4:47 PM  
Done.

Archit  4:57 PM  
CPU results look stable after the first few warmup requests. Average latency is around ~2s, but p95 is still high because of warmups.

CTO  4:57 PM  
I don’t see improvement because of the CPU image itself. The improvements mostly come from having more CPU cores.  
I’m fine with CPU for simplicity, but it doesn’t help latency much.


January 20, 2026

Archit  11:29 PM  
What latency targets do you want us to aim for?

CTO  9:43 AM  
Ideally under 1s, or similar to what we have now.  
I’d like p95 to be within 1s, but I still need to test frontend behavior to be sure.

Archit  3:00 PM  
Got it. I’ve tried most xlarge and 2xlarge CPU instances and we’re not seeing meaningful improvements from instance changes alone.  
Next I can profile the conversion path or try a custom image that supports librosa and see if that path behaves better.

CTO  9:56 PM  
Yeah, try the docker image first. I’m finishing the refactor now.


January 27, 2026

CTO  3:00 AM  
I’m seeing an error when loading the Neuron model:  
Unknown type name '__torch__.torch.classes.neuron.Model'.  
This line seems problematic. Can you try deploying the code in my repo?

Archit  9:47 AM  
This might be due to missing torch_neuron import before loading the model. I’ve seen a similar issue earlier.

CTO  9:51 AM  
I used inf1.xlarge and your container image. Instance type should be correct.

Archit  9:56 AM  
I’ll deploy on my side this afternoon and check.

CTO  12:14 PM  
You’re right. Deployment works after that fix.

Archit  1:25 PM  
Yeah, torch_neuron import was missing earlier. After adding it, deployment worked.  
Do you want me to run any specific tests now?

CTO  1:28 PM  
Check the code I pushed first. I’ll also run more tests on my side.




January 29, 2026

Archit [11:06 AM]  
Deployed the final version.

Archit [11:07 AM]  
Monitoring closely, but things look good so far.

CTO [11:15 AM]
Cool! Inferentia is saving around 70% of overall cost


