// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models
import software.amazon.awssdk.arns.Arn

case class ReferenceStoreItem(referenceArn: String, referenceStoreId: String, referenceId: String)

object ReferenceStoreItem {
  def apply(referenceArn: String): ReferenceStoreItem = {
    val arn = Arn.fromString(referenceArn)
    val arnResource = arn.resource()
    val referenceStoreId = arnResource.resource()
    val referenceId = arnResource.qualifier().get().split("/").last
    new ReferenceStoreItem(referenceArn, referenceStoreId, referenceId)
  }
}
