// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.common

import com.amazon.vincent.job.{TestSysProp}
import org.junit.runner.RunWith
import org.scalatest.funsuite.AnyFunSuite
import org.scalatestplus.junit.JUnitRunner
import software.amazon.awssdk.services.omics.OmicsClient

@RunWith(classOf[JUnitRunner])
class VincentGlueJobProviderTest extends AnyFunSuite with TestSysProp {

  test("ensure vincent glue job component returns omics client") {
    assert(AWSClientProvider.getOmicsClient.isInstanceOf[OmicsClient])
  }

  test("ensure vincent glue job component returns referenceStore dao") {
    assert(AWSClientProvider.getReferenceStoreDao().isInstanceOf[ReferenceStoreDao])
  }
}
