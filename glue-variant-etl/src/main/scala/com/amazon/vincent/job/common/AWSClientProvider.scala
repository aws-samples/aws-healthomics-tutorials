// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.common

import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration
import software.amazon.awssdk.core.retry.backoff.{BackoffStrategy, FullJitterBackoffStrategy}
import software.amazon.awssdk.core.retry.conditions.RetryCondition
import software.amazon.awssdk.core.retry.{RetryPolicy, RetryPolicyContext}
import software.amazon.awssdk.http.urlconnection.UrlConnectionHttpClient
import software.amazon.awssdk.services.omics.OmicsClient
import software.amazon.awssdk.services.omics.model.ThrottlingException
import java.time.Duration

object AWSClientProvider {

  /**
   * Provides Omics Client with retry policy configured
   *
   * Retry policy is configured to handle throttling encountered with the GetReference API on the
   * sequence store.
   *
   * @return
   *   omicsClient
   */
  def getOmicsClient: OmicsClient = {
    val retryCondition = new RetryCondition {
      override def shouldRetry(context: RetryPolicyContext): Boolean = {
        context.exception().isInstanceOf[ThrottlingException] ||
        (
          context.httpStatusCode() != null &&
            context.httpStatusCode() == 400 &&
            context.exception().getMessage != null &&
            context
              .exception()
              .getMessage
              .contains("Service returned error code RequestAbortedException")
        )
      }
    }
    val retryPolicy = RetryPolicy
      .defaultRetryPolicy()
      .toBuilder
      .retryCondition(retryCondition)
      .backoffStrategy(
        FullJitterBackoffStrategy
          .builder()
          .baseDelay(Duration.ofMillis(500L))
          .maxBackoffTime(Duration.ofSeconds(5))
          .build())
      .throttlingBackoffStrategy(BackoffStrategy.defaultThrottlingStrategy())
      .numRetries(3)
      .build()

    OmicsClient
      .builder()
      .overrideConfiguration(
        ClientOverrideConfiguration
          .builder()
          .retryPolicy(retryPolicy)
          .build())
      .httpClientBuilder(UrlConnectionHttpClient.builder())
      .build()
  }

  def getReferenceStoreDao(omicsClient: OmicsClient = getOmicsClient): ReferenceStoreDao =
    ReferenceStoreDao(omicsClient)
}
